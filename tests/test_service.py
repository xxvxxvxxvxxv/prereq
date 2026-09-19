import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
from prereq.catalog import CatalogError,degree_url,course_url
from prereq.network import OfficialClient,validate_url,PinnedHTTPS
from prereq.service import CatalogService,Store
from prereq.app import App,ROOT
from tests.fixtures import degree,pool,terms,pool_url,course

class MockOfficial:
    offline=False
    def __init__(self):
        self.urls=[];self.fail_area=False
    def get(self,url):
        self.urls.append(url)
        if url==degree_url('BSCS'): return terms(),url
        if url==degree_url('BSCS','202401'): return degree(),url
        for cat,cid in [('core','CS 201'),('area','CS 300'),('free','ECON 201')]:
            if url==pool_url('BSCS','202401',cat):
                if cat=='area' and self.fail_area: return '<p>Sign in</p>',url
                return pool(cid=cid),url
        if url==course_url('EE 202'): return course(),url
        raise AssertionError('Unexpected URL: '+url)

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.client=MockOfficial()
        self.service=CatalogService(ROOT,Path(self.temp.name)/'test.sqlite3',client=self.client)
    def tearDown(self):
        self.service.close();self.temp.cleanup()
    def test_end_to_end_fetch_discovers_all_three_pool_links(self):
        result=self.service.load('degree:BSCS:202401')
        self.assertEqual(len(result['sections']),5)
        self.assertTrue(all(s['courses'] for s in result['sections']))
        self.assertEqual(result['origin'],'live')
        self.assertEqual(len(result['provenance']),4)
        self.assertTrue(any('AEL' in url for url in self.client.urls))
    def test_no_wrong_major_fallback(self):
        self.assertIsNone(self.service.fallback('degree:BSCS:202401'))
        self.assertIsNone(self.service.fallback('degree:BSEE:202601'))
        self.assertEqual(len(self.service.fallback('degree:BSEE:202401')['sections'][4]['courses']),406)
    def test_atomic_snapshot_kept_after_pool_failure(self):
        key='degree:BSCS:202401'
        result=self.service.load(key);self.service.store.put(key,result)
        old,saved=self.service.store.get(key)
        self.client.fail_area=True
        self.service.jobs[key]=dict(running=True,started=time.time())
        self.service._refresh(key)
        new,new_saved=self.service.store.get(key)
        self.assertEqual(old,new);self.assertEqual(saved,new_saved)
        self.assertIsNotNone(self.service.jobs[key]['error'])
    def test_background_single_flight(self):
        event=threading.Event();calls=[]
        def slow(key):
            calls.append(key);event.wait(2)
            return dict(origin='live',observedAt='test')
        self.service.load=slow
        for _ in range(20):self.service.schedule('course:EE 202')
        event.set();self.service.executor.shutdown(wait=True)
        self.assertEqual(len(calls),1)
    def test_store_roundtrip_with_non_ascii(self):
        self.service.store.put('a',{'text':'Sabancı · Çığ'})
        self.assertEqual(self.service.store.get('a')[0],{'text':'Sabancı · Çığ'})
    def test_offline_retains_original_observation(self):
        self.service.client=OfficialClient(offline=True)
        result=self.service.get('degree:BSEE:202401')
        self.service.executor.shutdown(wait=True)
        result=self.service.get('degree:BSEE:202401')
        self.assertEqual(result['meta']['state'],'snapshot')
        self.assertEqual(result['meta']['observedAt'],'2026-09-17')
        self.assertIn('Offline mode',result['meta']['error'])
    def test_public_api_status_and_security_headers(self):
        app=App(root=ROOT,service=self.service)
        status,headers,payload=self.call(app,'/api/programs')
        self.assertEqual(status,'200 OK');self.assertEqual(len(payload['programs']),12)
        self.assertIn("object-src 'none'",headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Frame-Options'],'DENY')
        self.assertNotIn('Access-Control-Allow-Origin',headers)
    def test_host_allowlist(self):
        app=App(service=self.service)
        self.assertEqual(self.call(app,'/api/programs',host='attacker.example')[0],'403 Forbidden')
    def test_cross_site_blocked(self):
        app=App(service=self.service)
        self.assertEqual(self.call(app,'/api/programs',HTTP_SEC_FETCH_SITE='cross-site')[0],'403 Forbidden')
        self.assertEqual(self.call(app,'/api/programs',HTTP_X_PREREQ_CLIENT='')[0],'403 Forbidden')
    def test_path_traversal_and_private_files(self):
        app=App(service=self.service)
        for path in ('/../start.py','/.cache/catalog.sqlite3','/data/free.tsv','/.git/config'):
            self.assertEqual(self.call(app,path)[0],'404 Not Found')
    def test_arbitrary_fetch_and_duplicate_queries_rejected(self):
        app=App(service=self.service)
        for query in ('program=BSEE&term=202401&url=https://evil.example','program=BSEE&program=BSCS&term=202401','program=BSEE&term=../../'):
            self.assertEqual(self.call(app,'/api/degree',query=query)[0],'400 Bad Request')
    def test_refresh_post_only_and_origin_checked(self):
        app=App(service=self.service)
        self.assertEqual(self.call(app,'/api/refresh',query='program=BSEE&term=202401')[0],'405 Method Not Allowed')
        self.assertEqual(self.call(app,'/api/refresh',method='POST',query='program=BSEE&term=202401',HTTP_ORIGIN='https://evil.example')[0],'403 Forbidden')
    @staticmethod
    def call(app,path,method='GET',query='',host='127.0.0.1:8765',**extra):
        env=dict(REQUEST_METHOD=method,PATH_INFO=path,QUERY_STRING=query,HTTP_HOST=host,REMOTE_ADDR='127.0.0.1',HTTP_X_PREREQ_CLIENT='1',CONTENT_LENGTH='0')
        env['wsgi.url_scheme']='http';env.update(extra)
        result={}
        def start(status,headers):result.update(status=status,headers=dict(headers))
        body=b''.join(app(env,start))
        payload=json.loads(body) if result['headers']['Content-Type'].startswith('application/json') else body
        return result['status'],result['headers'],payload

class NetworkTests(unittest.TestCase):
    def test_upstream_allowlist(self):
        self.assertEqual(validate_url(course_url('EE 202')),course_url('EE 202'))
        for url in ('http://suis.sabanciuniv.edu/prod/SU_DEGREE.p_select_term',
                    'https://127.0.0.1/robots.txt','https://suis.sabanciuniv.edu.evil.test/robots.txt',
                    'https://user:pass@suis.sabanciuniv.edu/robots.txt',
                    'https://suis.sabanciuniv.edu:8443/robots.txt',
                    'https://suis.sabanciuniv.edu/.env','https://suis.sabanciuniv.edu/robots.txt?url=x',
                    'https://suis.sabanciuniv.edu/prod/SU_DEGREE.p_select_term?P_LANG=EN&P_LANG=TR'):
            with self.assertRaises(CatalogError):validate_url(url)
    def test_nonpublic_dns_blocked(self):
        import socket
        for ip in ('127.0.0.1','10.0.0.1','169.254.169.254','::1'):
            with patch('socket.getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))]):
                with self.assertRaises(CatalogError):PinnedHTTPS('suis.sabanciuniv.edu').connect()
    def test_robots_denial(self):
        c=OfficialClient();c._request=lambda url:(200,'User-agent: *\nDisallow: /prod/',url)
        with self.assertRaises(CatalogError):c.get(course_url('EE 202'))
    def test_robots_error_fails_closed(self):
        c=OfficialClient();c._request=lambda url:(503,'',url)
        with self.assertRaises(CatalogError):c.get(course_url('EE 202'))
    def test_robots_404_allows_public_fetch(self):
        c=OfficialClient()
        c._request=lambda url:(404,'',url) if url.endswith('robots.txt') else (200,'<p>public</p>',url)
        self.assertEqual(c.get(course_url('EE 202'))[0],'<p>public</p>')
    def test_offline_never_connects(self):
        c=OfficialClient(offline=True)
        c._request=lambda url:self.fail('Offline mode attempted a network call')
        with self.assertRaises(CatalogError):c.get(course_url('EE 202'))

if __name__=='__main__':unittest.main()
