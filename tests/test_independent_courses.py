"""Reproduce the 2.2 whole-catalog gate without contacting any external host.

Responses here are synthetic. Passing these tests proves routing and isolation,
not that the real university accepts the exact-course query from a deployed host.
"""
import copy
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from prereq.app import App, ROOT
from prereq.banner import BannerAdapter, CATALOG_SEARCH, CATALOG_START, course_form, parse_entries, parse_detail
from prereq.catalog import CatalogError, PROGRAM_MAP, code
from prereq.service import CatalogService, TTL
from tests import banner_fixtures as f
from tests import test_service as service_helpers


class ExactClient:
    offline = False

    def __init__(self, prereq='Undergraduate level NS 201 Minimum Grade of D'):
        self.calls = []
        self.prereq = prereq
        self.gate = None
        self.entered = threading.Event()

    def post(self, url, fields):
        self.calls.append(('POST', url, list(fields)))
        q = parse_qs(__import__('urllib.parse', fromlist=['urlencode']).urlencode(fields), keep_blank_values=True)
        subjects = [x for x in q.get('sel_subj', []) if x != 'dummy']
        if url != CATALOG_SEARCH or len(subjects) != 1 or q.get('sel_crse_strt') != q.get('sel_crse_end') or not q.get('sel_crse_strt', [''])[0]:
            raise CatalogError('Synthetic whole-catalog outage: exact-course queries only.')
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        cid = code(subjects[0] + q['sel_crse_strt'][0])
        return f.listing([cid], q['term_in'][0]), url

    def get(self, url):
        self.calls.append(('GET', url, None))
        if 'bwckctlg.p_disp_course_detail?' not in url:
            raise CatalogError('Synthetic whole-catalog outage: selector/index unavailable.')
        q = parse_qs(urlsplit(url).query)
        cid = code(q['subj_code_in'][0] + q['crse_numb_in'][0])
        return f.detail(cid, q['cat_term_in'][0], self.prereq, cid+'L'), url


def one_course_degree(program, cid):
    return {'program':dict(PROGRAM_MAP[program]), 'term':'202401', 'termLabel':'Fall 2024–2025',
            'sections':[{'id':'required', 'category':'required', 'courses':[{'code':cid, 'title':'Synthetic routing fixture'}]}],
            'complete':True, 'origin':'test-fixture'}


class CourseIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = ExactClient()
        self.service = CatalogService(ROOT, Path(self.temp.name)/'cache.db', client=self.client)

    def tearDown(self):
        if self.client.gate:
            self.client.gate.set()
        self.service.close()
        self.temp.cleanup()

    def wait_index(self, program='BSBIO'):
        key = f'degree:{program}:202401:202601'
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            with self.service.lock:
                running = self.service.index_jobs.get(key, {}).get('running')
            if running is False:
                return
            time.sleep(.005)
        self.fail('Synthetic index did not finish.')

    def test_exact_bio_detail_does_not_need_aggregate_catalog(self):
        d = self.service.load('course:202601:BIO 303')
        self.assertEqual(d['code'], 'BIO 303')
        self.assertEqual(d['catalogTerm'], '202601')
        self.assertEqual(d['prerequisite']['code'], 'NS 201')
        self.assertEqual(d['corequisite']['code'], 'BIO 303L')
        self.assertEqual([x[0] for x in self.client.calls], ['POST','GET'])
        self.assertIsNone(self.service.store.get('catalog:202601')[0])

    def test_explicit_full_catalog_failure_does_not_poison_individual_read(self):
        with self.assertRaises(CatalogError):
            self.service.load('catalog:202601')
        self.assertEqual(self.service.load('course:202601:BIO 303')['code'], 'BIO 303')

    def test_graph_index_starts_without_any_catalog_snapshot(self):
        self.service.store.put('degree:BSBIO:202401', one_course_degree('BSBIO','BIO 303'))
        self.service.graph_index('BSBIO','202401','202601')
        self.wait_index()
        r = self.service.graph_index('BSBIO','202401','202601')
        self.assertEqual(set(r['data']['details']), {'BIO 303'})
        self.assertEqual(r['meta']['loaded'], 1)
        self.assertIsNone(r['meta']['catalogTotal'])
        self.assertFalse(r['meta']['refreshing'])
        self.assertFalse(any(x[1] == CATALOG_START for x in self.client.calls))

    def test_course_api_completes_with_unavailable_aggregate_catalog(self):
        app = App(service=self.service)
        query = 'code=BIO%20303&catalogTerm=202601'
        service_helpers.ServiceTests.call(app, '/api/course', query=query)
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            status, _, result = service_helpers.ServiceTests.call(app, '/api/course', query=query)
            if result['data']:
                break
            time.sleep(.01)
        self.assertEqual(status, '200 OK')
        self.assertEqual(result['data']['prerequisite']['code'], 'NS 201')
        self.assertIsNone(self.service.store.get('catalog:202601')[0])

    def test_all_twelve_major_ids_route_to_their_own_course_fixture(self):
        # These identifiers exercise the generic path, not real degree content.
        examples={'BSEE':'EE 202','BSCS':'CS 204','BSDSA':'DSA 201','BSMS':'IE 301',
                  'BSMAT':'MAT 301','BSME':'ME 301','BSBIO':'BIO 303','BAECON':'ECON 201',
                  'BAPSIR':'PSIR 301','BAPSY':'PSY 201','BAVACD':'VA 301','BAMAN':'MGMT 201'}
        self.assertEqual(set(examples), set(PROGRAM_MAP))
        for program,cid in examples.items():
            with self.subTest(program=program):
                self.service.store.put(f'degree:{program}:202401', one_course_degree(program,cid))
                self.service.graph_index(program,'202401','202601')
                self.wait_index(program)
                r = self.service.graph_index(program,'202401','202601')
                self.assertEqual(r['data']['program'], program)
                self.assertEqual(set(r['data']['details']), {cid})
        self.assertFalse(any(x[1] == CATALOG_START for x in self.client.calls))

    def test_an_existing_but_incomplete_aggregate_is_not_a_gate(self):
        self.service.store.put('catalog:202601', {'catalogTerm':'202601','courses':{},'details':{}})
        self.assertEqual(self.service.load('course:202601:BIO 303')['code'],'BIO 303')

    def test_same_course_is_shared_across_majors_not_refetched(self):
        for program in ['BSEE','BSBIO']:
            self.service.store.put(f'degree:{program}:202401', one_course_degree(program,'CS 204'))
            self.service.graph_index(program,'202401','202601')
            if program=='BSEE':self.wait_index(program)
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(self.service.graph_index('BSBIO','202401','202601')['data']['details']['CS 204']['code'],'CS 204')

    def test_parallel_course_requests_share_one_source_response(self):
        self.client.gate = threading.Event()
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs=[pool.submit(self.service.load,'course:202601:BIO 303') for _ in range(4)]
            self.assertTrue(self.client.entered.wait(2))
            self.client.gate.set()
            records=[j.result(timeout=5) for j in jobs]
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(len({r['observedAt'] for r in records}), 1)

    def test_each_catalog_term_has_its_own_rules(self):
        self.service.load('course:202601:BIO 303')
        self.client.prereq='Undergraduate level NS 207 Minimum Grade of C'
        later=self.service.load('course:202602:BIO 303')
        self.assertEqual(later['prerequisite']['code'],'NS 207')
        self.assertEqual(self.service.load('course:202601:BIO 303')['prerequisite']['code'],'NS 201')

    def test_fresh_aggregate_detail_keeps_its_real_observation_date(self):
        item = parse_detail(f.detail('BIO 303'),'BIO 303','202601',f.detail_url('BIO 303'))
        stamp='2026-09-16T12:00:00+00:00'
        provenance=[{'url':'https://suis.sabanciuniv.edu/prod/bwckctlg.p_display_courses','retrievedAt':stamp}]
        self.service.store.put('catalog:202601',{'catalogTerm':'202601','courses':{'BIO 303':{}},
            'details':{'BIO 303':item},'observedAt':stamp,'provenance':provenance})
        d=self.service.load('course:202601:BIO 303')
        self.assertEqual(d['observedAt'],stamp)
        self.assertEqual(d['provenance'],provenance)
        self.assertEqual(self.client.calls,[])

    def test_current_read_and_pause_are_exposed_in_progress(self):
        self.service.store.put('degree:BSBIO:202401',one_course_degree('BSBIO','BIO 303'))
        self.client.gate=threading.Event()
        self.service.graph_index('BSBIO','202401','202601')
        self.assertTrue(self.client.entered.wait(2))
        r=self.service.graph_index('BSBIO','202401','202601')
        self.assertEqual(r['meta']['currentCourse'],'BIO 303')
        self.assertTrue(r['meta']['refreshing'])
        self.client.gate.set();self.wait_index()
        self.assertIsNone(self.service.graph_index('BSBIO','202401','202601')['meta']['currentCourse'])

    def test_unknown_prerequisite_is_loaded_but_needs_review(self):
        self.client.prereq='Instructor approval'
        self.service.store.put('degree:BSBIO:202401',one_course_degree('BSBIO','BIO 303'))
        self.service.graph_index('BSBIO','202401','202601');self.wait_index()
        r=self.service.graph_index('BSBIO','202401','202601')
        self.assertEqual(r['meta']['loaded'],1)
        self.assertEqual(r['meta']['reviewRequired'],1)
        self.assertEqual(r['data']['details']['BIO 303']['prerequisite']['type'],'unknown')

    def test_refresh_does_not_launch_a_whole_university_request(self):
        app=App(service=self.service)
        self.service.schedule=lambda key,force=False: self.assertFalse(key.startswith('catalog:'))
        status,_,_=service_helpers.ServiceTests.call(app,'/api/refresh',method='POST',
            query='program=BSBIO&term=202401&catalogTerm=202601')
        self.assertEqual(status,'200 OK')


class ExactAdapterTests(unittest.TestCase):
    def test_exact_query_keeps_dummy_repetition_blanks_and_course_bounds(self):
        fields=course_form('BIO 303','202601')
        self.assertEqual([v for k,v in fields if k=='sel_subj'],['dummy','BIO'])
        self.assertIn(('sel_crse_strt','303'),fields);self.assertIn(('sel_crse_end','303'),fields)
        self.assertIn(('sel_title',''),fields);self.assertIn(('term_in','202601'),fields)
        self.assertEqual([v for k,v in fields if k=='sel_levl'],['dummy','%'])

    def test_cached_validated_link_goes_straight_to_detail(self):
        client=ExactClient();item=parse_entries(f.listing(['BIO 303']),'202601')['courses']['BIO 303']
        reader=lambda url,fields=None:client.get(url) if fields is None else client.post(url,fields)
        d=BannerAdapter(reader).course('BIO 303','202601',item)
        self.assertEqual(d['code'],'BIO 303');self.assertEqual(len(client.calls),1)
        self.assertEqual(client.calls[0][0],'GET')

    def test_broader_response_cannot_substitute_another_course(self):
        def read(url,fields=None):return f.listing(['BIO 303L','EE 202']),url
        with self.assertRaises(CatalogError):BannerAdapter(read).course('BIO 303','202601')

    def test_extra_companion_records_do_not_block_exact_match(self):
        def read(url,fields=None):
            if fields is not None:return f.listing(['BIO 303','BIO 303L']),url
            self.assertEqual(url,f.detail_url('BIO 303'))
            return f.detail('BIO 303',prereq='NS 201',coreq='BIO 303L'),url
        self.assertEqual(BannerAdapter(read).course('BIO 303','202601')['prerequisite']['code'],'NS 201')

    def test_wrong_response_term_is_rejected(self):
        def read(url,fields=None):return f.listing(['BIO 303'],'202602'),url
        with self.assertRaises(CatalogError):BannerAdapter(read).course('BIO 303','202601')

    def test_no_courses_does_not_invent_no_prerequisites(self):
        def read(url,fields=None):return f.page('No courses found.'),url
        with self.assertRaises(CatalogError):BannerAdapter(read).course('BIO 303','202601')

    def test_unknown_requirement_cannot_become_eligibility(self):
        client=ExactClient(prereq='Junior standing and NS 201')
        reader=lambda url,fields=None:client.get(url) if fields is None else client.post(url,fields)
        self.assertEqual(BannerAdapter(reader).course('BIO 303','202601')['prerequisite']['type'],'unknown')

    def test_minimum_grades_logic_and_lab_are_preserved(self):
        client=ExactClient(prereq='(Undergraduate level NS 201 Minimum Grade of D or Undergraduate level BIO 301 Minimum Grade of C) and Undergraduate level BIO 332 Minimum Grade of D')
        reader=lambda url,fields=None:client.get(url) if fields is None else client.post(url,fields)
        d=BannerAdapter(reader).course('BIO 303','202601')
        self.assertEqual(d['prerequisite']['type'],'and')
        choice=d['prerequisite']['children'][0]
        self.assertEqual(choice['type'],'or');self.assertEqual(choice['children'][1]['minGrade'],'C')
        self.assertEqual(d['corequisite']['code'],'BIO 303L')

    def test_multiple_class_tokens_and_nttitle_are_supported(self):
        for cls in ['nttitle','ddtitle extra','extra nttitle']:
            with self.subTest(cls=cls):
                html=f.detail('BIO 303').replace('class="ddtitle"',f'class="{cls}"')
                self.assertEqual(parse_detail(html,'BIO 303','202601',f.detail_url('BIO 303'))['code'],'BIO 303')

    def test_other_course_heading_mentioning_target_is_rejected(self):
        html=f.detail('CS 204').replace('CS 204 - Test title','CS 204 - Test title mentions BIO 303')
        with self.assertRaises(CatalogError):parse_detail(html,'BIO 303','202601',f.detail_url('BIO 303'))

    def test_cached_other_course_or_other_term_never_fetched(self):
        for cid,term in [('EE 202','202601'),('BIO 303','202602')]:
            with self.subTest(cid=cid,term=term):
                adapter=BannerAdapter(lambda *a:self.fail('Mismatched source was fetched'))
                with self.assertRaises(CatalogError):adapter.course('BIO 303','202601',{'source':f.detail_url(cid,term)})

if __name__=='__main__':unittest.main()
