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
from .banner import BannerAdapter, parse_detail
from urllib.parse import urlencode

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
            db.execute("DELETE FROM snapshots WHERE key IN (SELECT key FROM snapshots WHERE key LIKE 'course:%' ORDER BY saved DESC LIMIT -1 OFFSET 18000)")
            db.execute("DELETE FROM snapshots WHERE key IN (SELECT key FROM snapshots WHERE key LIKE 'degree:%' ORDER BY saved DESC LIMIT -1 OFFSET 96)")
    def close(self):
        pass  # Connections are per operation, not shared across threads.

class CatalogService:
    """Three independent datasets: cohort rules, term catalog, term schedule."""
    def __init__(self, root: Path, cache_path: Path, offline=False, client=None):
        self.root = Path(root)
        self.seed = json.loads((self.root/'web'/'seed.json').read_text(encoding='utf-8'))
        self.store = Store(cache_path)
        self.client = client or OfficialClient(offline)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='catalog')
        self.index_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='prerequisite-index')
        self.index_jobs = {}
        self.lock = threading.RLock()
        self.jobs = {}
        self.closed = False
        self._load_locks = [threading.RLock() for _ in range(64)]

    def fallback(self, key):
        kind, rest = key.split(':', 1)
        if kind == 'degree':
            return self.seed['degrees'].get(rest)
        if kind == 'course':
            if ':' in rest:
                term, cid = rest.split(':', 1)
                return self.seed.get('catalogDetails', {}).get(term, {}).get(cid)
            return self.seed.get('details', {}).get(rest)
        if kind == 'terms':
            terms = [dict(id=d['term'], label=d['termLabel']) for d in self.seed['degrees'].values()
                     if d['program']['id'] == rest]
            return dict(program=rest, terms=terms, origin='bundled', observedAt=self.seed.get('observedAt')) if terms else None
        if kind == 'catalogterms':
            options = self.seed.get('catalogTerms', [])
            return dict(terms=options, origin='bundled', observedAt=self.seed.get('observedAt')) if options else None
        return None

    def get(self, key, refresh=False):
        data, saved = self.store.get(key)
        if data is None:
            data = self.fallback(key)
        stale = not saved or time.time() - saved > TTL
        # Unversioned bundled examples are viewable, but are never promoted to
        # current, term-specific rules. The new UI always specifies catalogTerm.
        legacy = key.startswith('course:') and key.count(':') == 1
        if (stale or refresh) and not legacy and not getattr(self.client, 'offline', False):
            self.schedule(key, refresh)
        with self.lock:
            job = copy.copy(self.jobs.get(key, {}))
        origin = data.get('origin', 'cache') if data else None
        state = ('unavailable' if data is None else 'partial' if data.get('complete') is False
                 else 'snapshot' if origin in {'bundled', 'user-supplied-html'}
                 else 'stale' if stale else 'verified')
        return dict(data=data, meta=dict(state=state, refreshing=job.get('running', False),
            observedAt=data.get('observedAt') if data else None, lastAttempt=job.get('at'),
            error=job.get('error') or ('Offline mode: source checks are disabled.' if getattr(self.client, 'offline', False) else None), ttlSeconds=TTL, sourceRole=data.get('sourceRole') if data else key.split(':')[0],
            source='official public sources', offline=getattr(self.client, 'offline', False),
            catalogTerm=data.get('catalogTerm') if data else None,
            complete=data.get('complete') if data else False))

    def schedule(self, key, force=False):
        with self.lock:
            old = self.jobs.get(key, {})
            cooldown = 300 if old.get('error') else 60
            if self.closed or old.get('running') or time.time()-old.get('started', 0) < cooldown:
                return
            if sum(bool(j.get('running')) for j in self.jobs.values()) >= 12:
                self.jobs[key] = dict(running=False, error='Source queue is busy. Try again shortly.', started=time.time(), at=now_iso())
                return
            if len(self.jobs) > 1500:
                self.jobs = {k:v for k,v in self.jobs.items() if v.get('running') or time.time()-v.get('started', 0) < 300}
            self.jobs[key] = dict(running=True, started=time.time(), at=now_iso(), error=None)
            self.executor.submit(self._refresh, key)

    def _refresh(self, key):
        error = None
        try:
            self.store.put(key, self.load(key))
        except Exception as exc:
            error = str(exc) if isinstance(exc, CatalogError) else 'Could not reach or parse the official source. Previous data was kept.'
            LOG.warning('Source check failed for %s: %s', key, error)
        finally:
            with self.lock:
                if key in self.jobs:
                    self.jobs[key].update(running=False, error=error)

    def load(self, key):
        # Coalesce parallel requests for shared semester snapshots/course pages.
        # Fixed-size lock striping bounds memory even for arbitrary valid codes.
        guard = self._load_locks[int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 64]
        with guard:
            return self._load(key)

    def _load(self, key):
        kind, rest = key.split(':', 1)
        sources = []
        def read(url, fields=None):
            validate_url(url)
            html, final = self.client.get(url) if fields is None else self.client.post(url, fields)
            sources.append(dict(url=final, method='GET' if fields is None else 'POST',
                                sha256=hashlib.sha256(html.encode()).hexdigest(), retrievedAt=now_iso()))
            return html, final
        adapter = BannerAdapter(read)
        if kind == 'catalogterms':
            result = adapter.terms()
        elif kind == 'catalog':
            term = rest
            result = adapter.catalog(term)
            for cid, item in result.get('details', {}).items():
                record = dict(item, observedAt=now_iso(), origin='live', provenance=list(sources))
                self.store.put(f'course:{term}:{cid}', record)
        elif kind == 'terms':
            if rest not in PROGRAM_MAP:
                raise CatalogError('Unknown program.')
            html, url = read(degree_url(rest))
            result = dict(program=rest, terms=parse_terms(html, rest), source=url, sourceRole='admission-terms')
        elif kind == 'degree':
            program, term = rest.split(':')
            if program not in PROGRAM_MAP:
                raise CatalogError('Unknown program.')
            # Do not make the degree load depend on a separate term-selector
            # request succeeding. The response must identify BOTH p and term.
            url = ('https://www.sabanciuniv.edu/en/prospective-students/degree-detail?'
                   'SU_DEGREE.p_degree_detail?' + urlencode([
                       ('P_TERM', term), ('P_PROGRAM', program), ('P_SUBMIT', ''), ('P_LANG', 'EN'), ('P_LEVEL', 'UG')]))
            try:
                html, final = read(url)
                result = parse_degree(html, program, term, final)
            except CatalogError as exc:
                if any(x in str(exc) for x in ('HTTP 401', 'HTTP 403', 'HTTP 429', 'HTTP 503', 'verification page', 'cooldown')):
                    raise
                # Both are published official degree representations. No change
                # of term/program and no rewriting a redirect to a login page.
                html, final = read(degree_url(program, term))
                result = parse_degree(html, program, term, final)
            errors = []
            def load_section(section):
                parts = section.get('subsections')
                if parts:
                    for part in parts:
                        load_section(part)
                    section['courses'] = list({c['code']: c for part in parts for c in part['courses']}.values())
                    section['complete'] = all(p.get('complete', True) for p in parts)
                elif section['id'] in result['poolLinks']:
                    try:
                        pool_html, pool_url = read(result['poolLinks'][section['id']])
                        listed = parse_pool(pool_html, program, pool_url)
                        section['courses'] = list({c['code']:c for c in section['courses']+listed}.values())
                        section.update(source=pool_url, complete=True, dataStatus='checked-pool')
                    except CatalogError as exc:
                        section.update(complete=False, dataStatus='pool-unavailable', poolSource=result['poolLinks'][section['id']])
                        errors.append(section['label'] + ': ' + str(exc))
                else:
                    section['complete'] = True
                section['totalCourseOptions'] = len(section['courses']) if section.get('complete', True) else None
            for section in result['sections']:
                load_section(section)
            previous, _ = self.store.get(key)
            previous = previous or self.fallback(key)
            if previous and previous.get('complete', True):
                if errors:
                    raise CatalogError('An elective pool could not be checked. The previous complete degree snapshot was kept.')
                old_counts = {s['id']:len(s['courses']) for s in previous['sections']}
                for s in result['sections']:
                    old = old_counts.get(s['id'], 0)
                    if old >= 15 and len(s['courses']) < old * .75:
                        raise CatalogError('Unexpected major change in a course pool. Retaining the previous snapshot for review.')
            result.pop('poolLinks', None)
            result.update(sourceRole='degree-requirements', admissionTerm=term,
                          complete=not errors, poolErrors=errors)
        elif kind == 'course':
            if ':' not in rest:
                raise CatalogError('Choose a catalog term. Unversioned detail is available only as a labeled saved example.')
            term, cid = rest.split(':', 1)
            cid = code(cid)
            catalog, stamp = self.store.get('catalog:'+term)
            if not catalog or time.time()-stamp > TTL:
                catalog = self.load('catalog:'+term)
                self.store.put('catalog:'+term, catalog)
            item = catalog['courses'].get(cid)
            if not item:
                raise CatalogError(f'{cid} is not in the retrieved {term} catalog. Its prerequisites remain unknown for that term.')
            if cid in catalog.get('details', {}):
                result = catalog['details'][cid]
            else:
                html, source = read(item['source'])
                result = parse_detail(html, cid, term, source)
        elif kind == 'schedule':
            term, cid = rest.split(':', 1)
            catalog, _ = self.store.get('catalog:'+term)
            links = catalog.get('courses', {}).get(cid, {}).get('scheduleLinks', []) if catalog else []
            result = adapter.schedule(cid, term, links)
        else:
            raise CatalogError('Unknown resource.')
        result.update(observedAt=now_iso(), origin='live', provenance=sources)
        return result

    def _index_codes(self, degree):
        priority = {'university':0, 'required':1, 'core':2, 'area':3, 'free':4}
        ordered = sorted(degree['sections'], key=lambda s:priority.get(s['id'], 1))
        return list(dict.fromkeys(c['code'] for s in ordered for c in s['courses']))[:3000]

    def _cached_details(self, codes, catalog_term=None):
        prefix = f'course:{catalog_term}:' if catalog_term else 'course:'
        data, saved = {}, {}
        with self.store.connect() as db:
            for off in range(0, len(codes), 800):
                keys = [prefix+c for c in codes[off:off+800]]
                if not keys:
                    continue
                rows = db.execute('SELECT key,payload,saved FROM snapshots WHERE key IN ('+','.join('?' for _ in keys)+')', keys).fetchall()
                for k, body, stamp in rows:
                    cid = k[len(prefix):]
                    item = json.loads(body)
                    if catalog_term is None or item.get('catalogTerm') == catalog_term:
                        data[cid], saved[cid] = item, stamp
        seed_details = self.seed.get('catalogDetails', {}).get(catalog_term, {}) if catalog_term else self.seed.get('details', {})
        for cid in codes:
            if cid not in data and cid in seed_details:
                data[cid] = seed_details[cid]
        return data, saved

    def graph_index(self, program, term, catalog_term=None):
        key = f'degree:{program}:{term}'
        degree, _ = self.store.get(key)
        degree = degree or self.fallback(key)
        if not degree:
            return dict(data=None, meta=dict(refreshing=False, error='Degree requirements have not loaded yet.'))
        codes = self._index_codes(degree)
        details, saved = self._cached_details(codes, catalog_term)
        offline = getattr(self.client, 'offline', False)
        if catalog_term is None:
            return dict(data=dict(program=program, term=term, catalogTerm=None, details=details),
                        meta=dict(refreshing=False, offline=offline, total=len(codes), loaded=len(details),
                                  legacy=True, error=None, scope='Unversioned saved examples, not rules for a selected catalog term.'))
        catalog, catalog_saved = self.store.get('catalog:'+catalog_term)
        if not catalog or time.time()-catalog_saved > TTL:
            result = self.get('catalog:'+catalog_term)
            if not catalog:
                return dict(data=dict(program=program, term=term, catalogTerm=catalog_term, details=details),
                    meta=dict(refreshing=result['meta']['refreshing'], stage='catalog', error=result['meta']['error'],
                              total=len(codes), loaded=len(details), offline=offline))
        missing_catalog = [cid for cid in codes if cid not in catalog['courses']]
        pending = [cid for cid in codes if cid in catalog['courses'] and time.time()-saved.get(cid, 0) > TTL]
        job_key = key + ':' + catalog_term
        with self.lock:
            job = self.index_jobs.get(job_key, {})
            cooldown = 300 if job.get('error') else 60
            if pending and not offline and not self.closed and not job.get('running') and time.time()-job.get('started', 0) >= cooldown:
                if not any(j.get('running') for j in self.index_jobs.values()):
                    if len(self.index_jobs) >= 128:
                        self.index_jobs = {k:v for k,v in self.index_jobs.items() if v.get('running') or time.time()-v.get('started',0)<300}
                    job = dict(running=True, started=time.time(), at=now_iso(), error=None, attempted=0)
                    self.index_jobs[job_key] = job
                    self.index_executor.submit(self._build_index, job_key, pending, catalog_term)
                else:
                    job = dict(running=True, stage='queued', error=None)
            meta = dict(refreshing=bool(job.get('running')), error=job.get('error'), lastAttempt=job.get('at'),
                        offline=offline, attempted=job.get('attempted', 0), total=len(codes), loaded=len(details),
                        catalogTerm=catalog_term, catalogTotal=len(catalog['courses']),
                        missingFromCatalog=missing_catalog, degreeComplete=degree.get('complete', True))
        return dict(data=dict(program=program, term=term, catalogTerm=catalog_term, details=details), meta=meta)

    def _build_index(self, key, codes, catalog_term):
        failures = 0; error = None; deadline = time.monotonic() + 1200
        for cid in codes:
            if self.closed or time.monotonic() >= deadline:
                break
            cache_key = f'course:{catalog_term}:{cid}'
            previous, saved = self.store.get(cache_key)
            if previous and time.time()-saved < TTL:
                continue
            try:
                self.store.put(cache_key, self.load(cache_key))
                failures = 0
            except Exception as exc:
                failures += 1
                error = str(exc) if isinstance(exc, CatalogError) else 'Official catalog unavailable. Existing details were kept.'
                LOG.warning('Prerequisite detail check failed (%s): %s', cache_key, error)
            with self.lock:
                self.index_jobs[key]['attempted'] += 1
            if failures >= 3:
                break
        with self.lock:
            self.index_jobs[key].update(running=False, error=error)

    def close(self):
        with self.lock:
            self.closed = True
        self.index_executor.shutdown(wait=True, cancel_futures=True)
        self.executor.shutdown(wait=True, cancel_futures=True)
