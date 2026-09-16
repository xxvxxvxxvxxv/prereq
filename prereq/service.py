"""SQLite last-known-good cache; bounded background refresh and atomic snapshots."""
from __future__ import annotations
import copy
from contextlib import contextmanager
import hashlib
import json
import logging
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from .catalog import (CatalogError, PROGRAM_MAP, code, degree_url, course_url,
                      parse_terms, parse_degree, parse_pool, parse_course)
from .network import OfficialClient, validate_url

LOG = logging.getLogger('prereq')
TTL = 12*3600

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY, payload TEXT NOT NULL, saved REAL NOT NULL)')
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()
    def get(self,key):
        with self.connect() as db:
            row = db.execute('SELECT payload,saved FROM snapshots WHERE key=?',(key,)).fetchone()
        return (json.loads(row[0]),row[1]) if row else (None,0)
    def put(self,key,payload):
        body=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
        if len(body.encode())>8_000_000:
            raise CatalogError('Normalized snapshot exceeds size limit.')
        with self.connect() as db:
            db.execute('INSERT INTO snapshots VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,saved=excluded.saved',(key,body,time.time()))
            # Bound persistent storage. Active degree snapshots are retained longer than course detail entries.
            db.execute("DELETE FROM snapshots WHERE key IN (SELECT key FROM snapshots WHERE key LIKE 'course:%' ORDER BY saved DESC LIMIT -1 OFFSET 3000)")
            db.execute("DELETE FROM snapshots WHERE key IN (SELECT key FROM snapshots WHERE key LIKE 'degree:%' ORDER BY saved DESC LIMIT -1 OFFSET 96)")
    def close(self):
        pass  # Connections are per operation, not shared across threads.

class CatalogService:
    def __init__(self, root: Path, cache_path: Path, offline=False, client=None):
        self.root=root
        self.seed=json.loads((root/'web'/'seed.json').read_text(encoding='utf-8'))
        self.store=Store(cache_path)
        self.client=client or OfficialClient(offline)
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='catalog')
        self.index_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='prerequisite-index')
        self.index_jobs={}
        self.lock=threading.Lock()
        self.jobs={}
        self.closed=False
    def fallback(self,key):
        kind,rest=key.split(':',1)
        if kind=='degree':
            return self.seed['degrees'].get(rest)
        if kind=='course':
            return self.seed['details'].get(rest)
        if kind=='terms' and rest=='BSEE':
            return dict(program='BSEE',terms=[dict(id='202401',label='Fall 2024–2025')],origin='bundled',observedAt=self.seed['observedAt'])
        return None
    def get(self,key,refresh=False):
        data,saved=self.store.get(key)
        if data is None:
            data=self.fallback(key)
        stale=not saved or time.time()-saved>TTL
        if stale or refresh:
            self.schedule(key,refresh)
        with self.lock:
            job=copy.copy(self.jobs.get(key,{}))
        origin=data.get('origin','cache') if data else None
        return dict(data=data,meta=dict(
            state='unavailable' if data is None else 'snapshot' if origin=='bundled' else 'stale' if stale else 'verified',
            refreshing=job.get('running',False), observedAt=data.get('observedAt') if data else None,
            lastAttempt=job.get('at'), error=job.get('error'), ttlSeconds=TTL,
            source='official public catalog', offline=getattr(self.client,'offline',False)))
    def schedule(self,key,force=False):
        with self.lock:
            old=self.jobs.get(key,{})
            cooldown=300 if old.get('error') else 60
            if self.closed or old.get('running') or time.time()-old.get('started',0)<cooldown:
                return
            if sum(bool(j.get('running')) for j in self.jobs.values())>=12:
                self.jobs[key]=dict(running=False,error='Refresh queue is busy. Try again in a minute.',started=time.time(),at=now_iso())
                return
            if len(self.jobs)>1500:
                self.jobs={k:v for k,v in self.jobs.items() if v.get('running') or time.time()-v.get('started',0)<300}
            self.jobs[key]=dict(running=True,started=time.time(),at=now_iso(),error=None)
            self.executor.submit(self._refresh,key)
    def _refresh(self,key):
        error=None
        try:
            data=self.load(key)
            self.store.put(key,data)
        except Exception as exc:
            if isinstance(exc,CatalogError):
                error=str(exc)
            else:
                error='Could not reach or read the official catalog. The previous snapshot has been kept.'
            LOG.warning('Refresh failed (%s): %s',key,type(exc).__name__)
        finally:
            with self.lock:
                self.jobs[key].update(running=False,error=error)
    def load(self,key):
        kind,rest=key.split(':',1)
        sources=[]
        def fetch(url):
            validate_url(url)
            html,final=self.client.get(url)
            sources.append(dict(url=final,sha256=hashlib.sha256(html.encode()).hexdigest(),retrievedAt=now_iso()))
            return html,final
        if kind=='terms':
            if rest not in PROGRAM_MAP:
                raise CatalogError('Unknown program.')
            html,url=fetch(degree_url(rest))
            result=dict(program=rest,terms=parse_terms(html,rest),source=url)
        elif kind=='degree':
            program,term=rest.split(':')
            # Validate actual availability rather than inventing program/admission combinations.
            terms,saved=self.store.get('terms:'+program)
            if terms is None or time.time()-saved>TTL:
                terms=self.load('terms:'+program)
                self.store.put('terms:'+program,terms)
            if term not in {t['id'] for t in terms['terms']}:
                raise CatalogError('That admission term is not listed by the official catalog for this program.')
            html,url=fetch(degree_url(program,term))
            result=parse_degree(html,program,term,url)
            def load_section(section):
                if section.get('subsections'):
                    for part in section['subsections']:
                        load_section(part)
                    section['courses']=list({c['code']:c for part in section['subsections'] for c in part['courses']}.values())
                if section['id'] in result['poolLinks']:
                    pool_html,pool_url=fetch(result['poolLinks'][section['id']])
                    listed=parse_pool(pool_html,program,pool_url)
                    section['courses']=list({c['code']:c for c in section['courses']+listed}.values())
                    section['source']=pool_url
            for section in result['sections']:
                load_section(section)
            previous,_=self.store.get(key)
            previous=previous or self.fallback(key)
            if previous:
                old_counts={s['id']:len(s['courses']) for s in previous['sections']}
                for section in result['sections']:
                    old=old_counts.get(section['id'],0)
                    if old>=15 and len(section['courses'])<old*0.75:
                        raise CatalogError('A course pool unexpectedly shrank by over 25%. Retaining the old snapshot until the adapter/source is reviewed.')
            result.pop('poolLinks',None)
        elif kind=='course':
            cid=code(rest)
            html,url=fetch(course_url(cid))
            result=parse_course(html,cid,url)
        else:
            raise CatalogError('Unknown resource.')
        result.update(observedAt=now_iso(),origin='live',provenance=sources)
        return result
    def _index_codes(self, degree):
        priority={'university':0,'required':1,'core':2,'area':3,'free':4}
        ordered=sorted(degree['sections'],key=lambda section:priority.get(section['id'],1))
        return list(dict.fromkeys(c['code'] for section in ordered for c in section['courses']))[:1500]

    def _cached_details(self, codes):
        if not codes:
            return {},{}
        keys=['course:'+c for c in codes]
        with self.store.connect() as db:
            rows=db.execute('SELECT key,payload,saved FROM snapshots WHERE key IN ('+','.join('?' for _ in keys)+')', keys).fetchall()
        data={k.removeprefix('course:'):json.loads(body) for k,body,_ in rows}
        saved={k.removeprefix('course:'):stamp for k,_,stamp in rows}
        for cid in codes:
            if cid not in data and cid in self.seed['details']:
                data[cid]=self.seed['details'][cid]
        return data,saved

    def graph_index(self, program, term):
        """Read cached prerequisite facts and start ONE bounded shared index job.
        Nothing fetched on this endpoint is a user-supplied URL. Progress is
        available while the first index is being built; failures retain dates.
        """
        key=f'degree:{program}:{term}'
        degree,_=self.store.get(key)
        degree=degree or self.fallback(key)
        if not degree:
            return dict(data=None,meta=dict(refreshing=False,error='Load a matching degree snapshot before indexing prerequisites.'))
        codes=self._index_codes(degree)
        details,saved=self._cached_details(codes)
        pending=[cid for cid in codes if time.time()-saved.get(cid,0)>TTL]
        offline=getattr(self.client,'offline',False)
        with self.lock:
            job=self.index_jobs.get(key,{})
            cooldown=300 if job.get('error') else 60
            if pending and not offline and not self.closed and not job.get('running') and time.time()-job.get('started',0)>=cooldown:
                if not any(v.get('running') for v in self.index_jobs.values()):
                    if len(self.index_jobs)>96:
                        self.index_jobs={k:v for k,v in self.index_jobs.items() if v.get('running') or time.time()-v.get('started',0)<300}
                    job=dict(running=True,started=time.time(),at=now_iso(),error=None,attempted=0)
                    self.index_jobs[key]=job
                    self.index_executor.submit(self._build_index,key,pending)
                else:
                    job=dict(running=False,error='Another major is being checked. Its shared course cache remains available; retry later.')
            meta=dict(refreshing=bool(job.get('running')),error=job.get('error'),lastAttempt=job.get('at'),offline=offline,
                      attempted=job.get('attempted',0),total=len(codes),loaded=len(details))
        return dict(data=dict(program=program,term=term,details=details),meta=meta)

    def _build_index(self,key,codes):
        failures=0;error=None;deadline=time.monotonic()+1200
        for cid in codes:
            if self.closed or time.monotonic()>deadline:
                break
            previous,saved=self.store.get('course:'+cid)
            if previous and time.time()-saved<TTL:
                continue
            try:
                value=self.load('course:'+cid)
                self.store.put('course:'+cid,value)
                failures=0
            except Exception as exc:
                failures+=1
                error=str(exc) if isinstance(exc,CatalogError) else 'Official catalog unavailable. Checked prerequisite links have been kept.'
                LOG.warning('Prerequisite index read failed (%s): %s',cid,type(exc).__name__)
            with self.lock:
                self.index_jobs[key]['attempted']+=1
            # Stop early on unavailable/changed sources, rather than hammering
            # hundreds of URLs after an outage, robots block or parser change.
            if failures>=3:
                break
        with self.lock:
            self.index_jobs[key].update(running=False,error=error)

    def close(self):
        with self.lock:
            self.closed=True
        self.index_executor.shutdown(wait=True,cancel_futures=True)
        self.executor.shutdown(wait=True,cancel_futures=True)
