"""Dependency-free WSGI application. Production: serve with a managed WSGI server."""
from __future__ import annotations
from collections import OrderedDict, deque
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import json
import os
import re
import threading
import time
from . import __version__
from .catalog import PROGRAM_MAP, CatalogError, TERM_RE, code
from .service import CatalogService

ROOT=Path(__file__).resolve().parents[1]
STATIC={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/model.js':'model.js',
        '/styles.css':'styles.css','/favicon.svg':'favicon.svg','/seed.json':'seed.json'}
MIMES={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
       '.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.json':'application/json; charset=utf-8'}
HEADERS=[('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),
 ('Referrer-Policy','no-referrer'),('Permissions-Policy','camera=(), microphone=(), geolocation=()'),
 ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]

class RateLimit:
    def __init__(self):
        self.items=OrderedDict(); self.lock=threading.Lock()
    def allowed(self,client,limit=150):
        with self.lock:
            now=time.monotonic()
            q=self.items.setdefault(client,deque())
            while q and q[0]<now-60:
                q.popleft()
            self.items.move_to_end(client)
            while len(self.items)>1024:
                self.items.popitem(last=False)
            if len(q)>=limit:
                return False
            q.append(now)
            return True

class App:
    def __init__(self,root=ROOT,cache=None,offline=None,service=None):
        self.root=Path(root)
        self.service=service or CatalogService(self.root,Path(cache or os.environ.get('PREREQ_CACHE',self.root/'.cache'/'catalog.sqlite3')),
            offline=os.environ.get('PREREQ_OFFLINE')=='1' if offline is None else offline)
        self.hosts={'localhost','127.0.0.1','[::1]'} | {x.strip().lower() for x in os.environ.get('PREREQ_HOSTS','').split(',') if x.strip()}
        # Render supplies this exact hostname as an environment variable. Do not
        # accept wildcard hosts or trust a user-controlled X-Forwarded-Host.
        render_host=os.environ.get('RENDER_EXTERNAL_HOSTNAME','').strip().lower()
        if render_host:
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.onrender\.com',render_host):
                raise ValueError('RENDER_EXTERNAL_HOSTNAME must be one exact onrender.com hostname.')
            self.hosts.add(render_host)
        # An explicit public scheme handles TLS termination without trusting
        # arbitrary incoming forwarded-protocol headers. Render serves HTTPS.
        self.public_scheme=os.environ.get('PREREQ_PUBLIC_SCHEME','').strip().lower()
        if self.public_scheme not in {'','http','https'}:
            raise ValueError('PREREQ_PUBLIC_SCHEME must be http or https when set.')
        self.rate=RateLimit()
    def __call__(self,environ,start_response):
        method=environ.get('REQUEST_METHOD','GET')
        path=environ.get('PATH_INFO','/')
        def respond(status,payload,mime='application/json; charset=utf-8',extra=None):
            body=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
            start_response(status,HEADERS+[('Content-Type',mime),('Content-Length',str(len(body))),('Cache-Control','no-store')]+(extra or []))
            return [b'' if method=='HEAD' else body]
        rawhost=environ.get('HTTP_HOST','')
        try:
            host=urlsplit('//'+rawhost).hostname or ''
            host='[::1]' if host=='::1' else host.lower()
            if host not in self.hosts or '@' in rawhost or '/' in rawhost:
                return respond('403 Forbidden',dict(error='Host is not allowed. Configure PREREQ_HOSTS for a public deployment.'))
            if method not in {'GET','HEAD','POST'}:
                return respond('405 Method Not Allowed',dict(error='Method not allowed.'),extra=[('Allow','GET, HEAD, POST')])
            if path=='/health' and method in {'GET','HEAD'}:
                return respond('200 OK',dict(status='ok',version=__version__))
            if path.startswith('/api/'):
                if environ.get('HTTP_SEC_FETCH_SITE')=='cross-site' or environ.get('HTTP_X_PREREQ_CLIENT')!='1':
                    return respond('403 Forbidden',dict(error='Same-origin application requests only.'))
                if not self.rate.allowed(environ.get('REMOTE_ADDR','unknown')):
                    return respond('429 Too Many Requests',dict(error='Too many requests. Try again in a minute.'),extra=[('Retry-After','60')])
                if len(environ.get('QUERY_STRING',''))>250:
                    raise CatalogError('Query exceeds size limit.')
                q=parse_qs(environ.get('QUERY_STRING',''),keep_blank_values=True,max_num_fields=4)
                if any(len(v)!=1 for v in q.values()):
                    raise CatalogError('Duplicate query parameters are not allowed.')
                if path=='/api/programs' and method=='GET':
                    return respond('200 OK',dict(programs=list(PROGRAM_MAP.values())))
                refresh=path=='/api/refresh'
                if refresh:
                    if method!='POST':
                        return respond('405 Method Not Allowed',dict(error='Refresh requires POST.'))
                    origin=environ.get('HTTP_ORIGIN')
                    expected=(self.public_scheme or environ.get('wsgi.url_scheme','http'))+'://'+rawhost
                    if origin and origin!=expected:
                        return respond('403 Forbidden',dict(error='Origin does not match this site.'))
                    if environ.get('CONTENT_LENGTH','0') not in {'','0'}:
                        raise CatalogError('Refresh accepts no request body.')
                elif method!='GET':
                    return respond('405 Method Not Allowed',dict(error='Read endpoints require GET.'))
                if path in {'/api/degree','/api/terms','/api/refresh','/api/index'}:
                    if set(q)-{'program','term'}:
                        raise CatalogError('Unsupported query parameter.')
                    program=q.get('program',[''])[0]
                    if program not in PROGRAM_MAP:
                        raise CatalogError('Select a supported major.')
                    if path=='/api/terms':
                        key='terms:'+program
                    else:
                        term=q.get('term',[''])[0]
                        if not TERM_RE.fullmatch(term):
                            raise CatalogError('Select a valid first admission term.')
                        if path=='/api/index':
                            return respond('200 OK',self.service.graph_index(program,term))
                        key=f'degree:{program}:{term}'
                elif path=='/api/course':
                    if set(q)!={'code'}:
                        raise CatalogError('A course code is required.')
                    key='course:'+code(q['code'][0])
                else:
                    return respond('404 Not Found',dict(error='Unknown API endpoint.'))
                return respond('200 OK',self.service.get(key,refresh=refresh))
            if method not in {'GET','HEAD'}:
                return respond('405 Method Not Allowed',dict(error='Method not allowed.'))
            if path not in STATIC:
                return respond('404 Not Found',dict(error='Not found.'))
            file=self.root/'web'/STATIC[path]
            return respond('200 OK',file.read_bytes(),MIMES[file.suffix])
        except (CatalogError,ValueError) as exc:
            return respond('400 Bad Request',dict(error=str(exc)))
        except Exception:
            import logging
            logging.getLogger('prereq').exception('Application request failed')
            return respond('500 Internal Server Error',dict(error='The request could not be completed. No cached snapshot was replaced.'))

# Lazy construction prevents a database write on parser/test imports.
_instance=None
_instance_lock=threading.Lock()
def application(environ,start_response):
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance=App()
    return _instance(environ,start_response)
