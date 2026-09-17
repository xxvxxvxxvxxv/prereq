"""Prerequisite indexing tests use mocks, never the university network."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from prereq.app import App, ROOT
from prereq.catalog import CatalogError, parse_course, course_url
from prereq.network import OfficialClient
from prereq.service import CatalogService, TTL
from tests import test_service as helpers
from tests.fixtures import course

class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.s=CatalogService(ROOT,Path(self.temp.name)/'index.sqlite3',offline=True)
    def tearDown(self):
        self.s.close();self.temp.cleanup()
    def test_offline_returns_partial_checked_details_without_scheduling(self):
        self.s.client.get=lambda url:self.fail('Offline index attempted network')
        r=self.s.graph_index('BSEE','202401')
        self.assertEqual(len(r['data']['details']),57)
        self.assertFalse(r['meta']['refreshing']);self.assertEqual(self.s.index_jobs,{})
    def test_no_degree_does_not_substitute_another_major(self):
        r=self.s.graph_index('BSCS','202401')
        self.assertIsNone(r['data']);self.assertFalse(r['meta']['refreshing'])
    def test_university_and_required_are_indexed_before_electives(self):
        d=self.s.fallback('degree:BSEE:202401');codes=self.s._index_codes(d)
        self.assertEqual(len(codes),624);self.assertLess(codes.index('IF 100'),codes.index('EE 202'))
        self.assertLess(codes.index('EE 202'),codes.index('EE 302'))
    def test_index_endpoint_requires_same_origin_header_and_valid_query(self):
        app=App(service=self.s)
        status,headers,body=helpers.ServiceTests.call(app,'/api/index',query='program=BSEE&term=202401')
        self.assertEqual(status,'200 OK');self.assertEqual(body['data']['program'],'BSEE')
        self.assertEqual(helpers.ServiceTests.call(app,'/api/index',query='program=BSEE&term=202401',HTTP_X_PREREQ_CLIENT='')[0],'403 Forbidden')
        for q in ['program=BSEE&term=202401&url=http://127.0.0.1','program=BSEE&program=BSCS&term=202401','program=BSEE&term=invalid']:
            self.assertEqual(helpers.ServiceTests.call(app,'/api/index',query=q)[0],'400 Bad Request')
    def test_index_coalesces_repeat_requests_into_one_worker(self):
        self.s.client.offline=False
        gate=threading.Event();calls=[]
        self.s._index_codes=lambda d:['EE 202']
        def load(key):
            calls.append(key);gate.wait(2)
            return dict(self.s.seed['details']['EE 202'],origin='live',catalogTerm='202601')
        self.s.load=load
        try:
            self.s.store.put('catalog:202601',{'courses':{'EE 202':{}},'catalogTerm':'202601'})
            for _ in range(12):self.s.graph_index('BSEE','202401','202601')
        finally:gate.set()
        self.s.index_executor.shutdown(wait=True)
        self.assertEqual(calls,['course:202601:EE 202'])
    def test_stops_after_three_consecutive_failures_and_preserves_date(self):
        old=dict(self.s.seed['details']['EE 202'],origin='live',catalogTerm='202601',observedAt='2020-01-01')
        self.s.store.put('course:202601:EE 202',old)
        with self.s.store.connect() as db:db.execute('UPDATE snapshots SET saved=? WHERE key=?',(time.time()-TTL-1,'course:202601:EE 202'))
        _,saved=self.s.store.get('course:202601:EE 202');calls=[]
        def fail(key):calls.append(key);raise CatalogError('Test unavailable')
        self.s.load=fail;key='degree:BSEE:202401';self.s.index_jobs[key]=dict(running=True,attempted=0)
        self.s._build_index(key,['EE 202','EE 200','CS 303','MATH 101'],'202601')
        self.assertEqual(len(calls),3);self.assertEqual(self.s.store.get('course:202601:EE 202'),(old,saved))
        self.assertFalse(self.s.index_jobs[key]['running'])
    def test_fresh_cache_does_not_trigger_an_index(self):
        self.s.client.offline=False;self.s._index_codes=lambda d:['EE 202']
        self.s.store.put('course:EE 202',dict(self.s.seed['details']['EE 202'],origin='live'))
        self.assertFalse(self.s.graph_index('BSEE','202401')['meta']['refreshing'])
        self.assertEqual(self.s.index_jobs,{})
    def test_preexisting_cache_overrides_bundled_detail_not_vice_versa(self):
        d=dict(self.s.seed['details']['EE 202'],observedAt='2026-09-17T12:00:00Z',origin='live')
        self.s.store.put('course:EE 202',d)
        values,saved=self.s._cached_details(['EE 202','MATH 101'])
        self.assertEqual(values['EE 202']['origin'],'live');self.assertEqual(values['MATH 101']['origin'],'bundled')
        self.assertIn('EE 202',saved);self.assertNotIn('MATH 101',saved)

class ContextParserTests(unittest.TestCase):
    def test_singular_credit_and_zero_credit_headings(self):
        for count in (0,1):
            html=course('EE 234',prereq='__',coreq='__').replace('3 Credits',f'{count} Credit')
            self.assertEqual(parse_course(html,'EE 234',course_url('EE 234'))['credits'],count)
    def test_description_only_cohort_restrictions_are_not_unconditional_none(self):
        html=course('ENS 491',prereq='__',coreq='ENS 491R').replace('Course description not used.','Program-specific prerequisite requirements depend on admission-year and completed credits.')
        d=parse_course(html,'ENS 491',course_url('ENS 491'))
        self.assertEqual(d['prerequisite']['type'],'unknown');self.assertIn('description',d['generalRequirements'])
    def test_description_caution_does_not_delete_explicit_expression(self):
        html=course().replace('Course description not used.','Additional program-specific conditions apply.')
        d=parse_course(html,'EE 202',course_url('EE 202'))
        self.assertEqual(d['prerequisite']['code'],'ENS 203');self.assertIn('official page',d['generalRequirements'])
