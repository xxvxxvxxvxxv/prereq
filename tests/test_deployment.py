"""Deployment configuration tests. No hosting or upstream network requests."""
import json
import os
import runpy
import unittest
from unittest.mock import patch
from prereq.app import App, ROOT
from prereq import __version__

class FakeService:
    def __init__(self): self.calls=[]
    def get(self,key,refresh=False):
        self.calls.append((key,refresh))
        return {"data":None,"meta":{"refreshing":False}}

class DeploymentTests(unittest.TestCase):
    def make(self,env):
        with patch.dict(os.environ,env,clear=True):
            return App(service=FakeService())
    def call(self,app,path='/health',host='demo.onrender.com',origin=None,extra=None):
        env={'REQUEST_METHOD':'POST' if path=='/api/refresh' else 'GET',
             'PATH_INFO':path,'QUERY_STRING':'program=BSEE&term=202401',
             'HTTP_HOST':host,'REMOTE_ADDR':'10.0.0.1','wsgi.url_scheme':'http',
             'HTTP_X_PREREQ_CLIENT':'1','CONTENT_LENGTH':'0'}
        if origin is not None:env['HTTP_ORIGIN']=origin
        env.update(extra or {})
        out={}
        def start(status,headers):out.update(status=status,headers=dict(headers))
        out['body']=b''.join(app(env,start))
        return out
    def test_render_hostname_auto_allowed(self):
        app=self.make({'RENDER_EXTERNAL_HOSTNAME':'demo.onrender.com'})
        result=self.call(app)
        self.assertEqual(result['status'],'200 OK')
        self.assertEqual(json.loads(result['body'])['version'],__version__)
    def test_other_render_tenant_not_allowed(self):
        app=self.make({'RENDER_EXTERNAL_HOSTNAME':'demo.onrender.com'})
        self.assertEqual(self.call(app,host='attacker.onrender.com')['status'],'403 Forbidden')
    def test_invalid_render_hostname_fails_closed(self):
        for host in ('*.onrender.com','https://demo.onrender.com','demo.onrender.com.evil.test','evil.test','demo.onrender.com:443','a@demo.onrender.com'):
            with self.subTest(host=host),self.assertRaises(ValueError):
                self.make({'RENDER_EXTERNAL_HOSTNAME':host})
    def test_custom_domain_is_explicitly_allowed(self):
        app=self.make({'RENDER_EXTERNAL_HOSTNAME':'demo.onrender.com','PREREQ_HOSTS':'courses.example.com,www.courses.example.com'})
        for host in ('courses.example.com','www.courses.example.com','demo.onrender.com'):
            self.assertEqual(self.call(app,host=host)['status'],'200 OK')
    def test_https_origin_works_behind_http_tls_terminator(self):
        app=self.make({'RENDER_EXTERNAL_HOSTNAME':'demo.onrender.com','PREREQ_PUBLIC_SCHEME':'https'})
        result=self.call(app,'/api/refresh',origin='https://demo.onrender.com')
        self.assertEqual(result['status'],'200 OK')
        self.assertEqual(app.service.calls,[('degree:BSEE:202401',True)])
    def test_other_origin_or_insecure_origin_is_rejected(self):
        app=self.make({'RENDER_EXTERNAL_HOSTNAME':'demo.onrender.com','PREREQ_PUBLIC_SCHEME':'https'})
        for origin in ('https://evil.example','http://demo.onrender.com','https://demo.onrender.com.evil.example'):
            self.assertEqual(self.call(app,'/api/refresh',origin=origin)['status'],'403 Forbidden')
        self.assertEqual(app.service.calls,[])
    def test_forwarded_headers_cannot_override_pinned_origin(self):
        app=self.make({'RENDER_EXTERNAL_HOSTNAME':'demo.onrender.com','PREREQ_PUBLIC_SCHEME':'https'})
        result=self.call(app,'/api/refresh',origin='http://evil.example',extra={'HTTP_X_FORWARDED_HOST':'evil.example','HTTP_X_FORWARDED_PROTO':'http'})
        self.assertEqual(result['status'],'403 Forbidden')
    def test_local_http_works_without_public_scheme(self):
        app=self.make({})
        self.assertEqual(self.call(app,'/api/refresh',host='127.0.0.1:8765',origin='http://127.0.0.1:8765')['status'],'200 OK')
    def test_invalid_public_scheme_fails_closed(self):
        with self.assertRaises(ValueError): self.make({'PREREQ_PUBLIC_SCHEME':'ftp'})
    def test_production_config_uses_host_port_and_one_worker(self):
        with patch.dict(os.environ,{'PORT':'10000'},clear=True):
            c=runpy.run_path(str(ROOT/'gunicorn.conf.py'))
        self.assertEqual(c['bind'],'0.0.0.0:10000')
        self.assertEqual(c['workers'],1)
        self.assertEqual(c['threads'],8)
        self.assertFalse(c['preload_app'])
        self.assertNotIn('*',c['forwarded_allow_ips'])
    def test_production_config_rejects_invalid_port(self):
        for port in ('0','65536','oops'):
            with self.subTest(port=port),patch.dict(os.environ,{'PORT':port},clear=True),self.assertRaises(ValueError):
                runpy.run_path(str(ROOT/'gunicorn.conf.py'))
    def test_blueprint_is_free_not_implicitly_billable(self):
        text=(ROOT/'render.yaml').read_text()
        self.assertIn('plan: free',text)
        self.assertIn('runtime: python',text)
        self.assertIn('healthCheckPath: /health',text)
        self.assertIn('PREREQ_PUBLIC_SCHEME',text)
        self.assertNotIn('    disk:',text)
