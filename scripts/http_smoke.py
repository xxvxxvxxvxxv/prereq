#!/usr/bin/env python3
"""Offline smoke checks over a real, temporary loopback WSGI HTTP server.
No external network calls, production writes or installed packages required.
This does not exercise Gunicorn, Render or production TLS.
"""
import os, sys, threading, tempfile, http.client, json
from pathlib import Path
from wsgiref.simple_server import make_server,WSGIRequestHandler
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from prereq.app import App
from prereq import __version__
class Quiet(WSGIRequestHandler):
    def log_message(self,*args):pass
checks=[]
with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'PREREQ_OFFLINE':'1','PREREQ_HOSTS':'','RENDER_EXTERNAL_HOSTNAME':'prereq-test.onrender.com','PREREQ_PUBLIC_SCHEME':'https'},clear=False):
    app=App(cache=Path(temp)/'test.sqlite3',offline=True)
    server=make_server('127.0.0.1',0,app,handler_class=Quiet)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def req(path,method='GET',extra=None,host='prereq-test.onrender.com'):
        c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        headers={'Host':host,'X-Prereq-Client':'1'};headers.update(extra or {})
        c.request(method,path,headers=headers);r=c.getresponse();body=r.read();headers=dict(r.getheaders());status=r.status;c.close()
        return status,headers,body
    def check(name,value):
        assert value,name
        checks.append(name);print('PASS',name)
    try:
        status,headers,body=req('/health')
        check('Local HTTP health endpoint serves version '+__version__,status==200 and json.loads(body)['version']==__version__)
        status,headers,body=req('/')
        check('Application HTML is served, not the offline preview',status==200 and b'__PREVIEW_SEED__' not in body and b'src="app.js"' in body)
        check('CSP and embedding protections survive real HTTP',headers.get('X-Frame-Options')=='DENY' and "frame-ancestors 'none'" in headers.get('Content-Security-Policy',''))
        status,headers,body=req('/app.js')
        check('Live application uses the empty expansion set',status==200 and b'function defaultExpanded(){return new Set();}' in body)
        status,headers,body=req('/api/programs')
        check('API is present with 12 program options',status==200 and len(json.loads(body)['programs'])==12)
        status,headers,body=req('/api/degree?program=BSEE&term=202401')
        check('Matching bundled degree remains available during offline operation',status==200 and json.loads(body)['data']['program']['id']=='BSEE')
        status,headers,body=req('/api/refresh?program=BSEE&term=202401','POST',{'Origin':'https://prereq-test.onrender.com'})
        check('HTTPS public Origin refresh works through an HTTP socket',status==200)
        check('Unrelated Origin fails through real HTTP',req('/api/refresh?program=BSEE&term=202401','POST',{'Origin':'https://evil.example'})[0]==403)
        check('Unrelated Render tenant hostname is rejected',req('/health',host='evil.onrender.com')[0]==403)
        check('Private cache files are not publicly served',req('/.cache/catalog.sqlite3')[0]==404)
        check('Public API responses are not cacheable',req('/api/programs')[1].get('Cache-Control')=='no-store')
    finally:
        server.shutdown();server.server_close();thread.join();app.service.close()
print(json.dumps({'passed':len(checks),'checks':checks,'scope':'Loopback WSGI HTTP with hosted Host/Origin headers, offline service; not a Gunicorn or live Render test.'},indent=2))
print(f'{len(checks)} loopback HTTP checks passed.')
