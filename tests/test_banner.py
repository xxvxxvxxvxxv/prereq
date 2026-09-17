"""New adapters: request-shape, strict parsing, and source separation tests.
These are local/synthetic tests, not proof of successful university fetching.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode,parse_qs,urlsplit
from prereq.banner import (BannerAdapter,CAPTURED_SUBJECTS,CATALOG_START,CATALOG_SEARCH,SCHEDULE_START,
    catalog_form,term_options,forms,form_fields,term_fields,parse_entries,parse_detail,parse_schedule,banner_expression)
from prereq.catalog import CatalogError,Document,PROGRAM_MAP,parse_degree,catalog_link,code
from prereq.app import App,ROOT
from prereq.service import CatalogService
from tests import banner_fixtures as f
from tests.fixtures import degree,pool
from tests import test_service as service_helpers

class FormTests(unittest.TestCase):
    def test_exact_captured_post_size_and_counts(self):
        fields=catalog_form('202601',CAPTURED_SUBJECTS)
        self.assertEqual((len(CAPTURED_SUBJECTS),len(fields),len(urlencode(fields).encode())),(74,94,1267))
    def test_repeated_subjects_and_dummy_preserved(self):
        q=parse_qs(urlencode(catalog_form('202601',['CS','BIO'])),keep_blank_values=True)
        self.assertEqual(q['sel_subj'],['dummy','CS','BIO']);self.assertEqual(q['sel_levl'],['dummy','%'])
        self.assertEqual(q['sel_title'],[''])
    def test_term_code_not_admission(self):
        self.assertEqual(catalog_form('202602',['BIO'])[0],('term_in','202602'))
    def test_invalid_input(self):
        for term,subjects in [('no',['CS']),('202601',[]),('202601',['CS','CS']),('202601',['../../'])]:
            with self.subTest(term=term,subjects=subjects),self.assertRaises(CatalogError):catalog_form(term,subjects)
    def test_actual_selector_field_names_are_used(self):
        for schedule,name in [(False,'cat_term_in'),(True,'p_term')]:
            html=f.selector(schedule);form,url=forms(html,CATALOG_START)[0]
            self.assertIn((name,'202601'),term_fields(form,'202601'))
            self.assertEqual(len(term_options(html)),2)
    def test_hidden_dummy_not_overwritten(self):
        form,_=forms(f.search(True),SCHEDULE_START)[0]
        fields=form_fields(form,{'term_in':'202601','sel_subj':'CS','sel_crse':'204'})
        self.assertEqual([v for k,v in fields if k=='sel_subj'],['dummy','CS'])
    def test_unknown_option_not_submitted(self):
        form,_=forms(f.selector(),CATALOG_START)[0]
        with self.assertRaises(CatalogError):term_fields(form,'203001')
    def test_password_form_rejected(self):
        form,_=forms('<form><input name="password" type="password"></form>',CATALOG_START)[0]
        with self.assertRaises(CatalogError):form_fields(form,{})
    def test_no_selector_not_invented(self):
        with self.assertRaises(CatalogError):term_options('<p>Server busy</p>')

class ExpressionTests(unittest.TestCase):
    def test_banner_undergraduate_minimum_grade(self):
        n=banner_expression('Undergraduate level CS 201 Minimum Grade of D')
        self.assertEqual(n['type'],'course');self.assertEqual(n['code'],'CS 201');self.assertEqual(n['minGrade'],'D')
    def test_and_or_and_parentheses_retained(self):
        n=banner_expression('(Undergraduate level CS 201 Minimum Grade of D or Undergraduate level IF 100 Minimum Grade of C) and Undergraduate level MATH 101 Minimum Grade of D')
        self.assertEqual(n['type'],'and');self.assertEqual(n['children'][0]['type'],'or')
    def test_concurrent_permission_retained(self):
        n=banner_expression('Course or Test: CS 201 Minimum Grade of D May be taken concurrently.')
        self.assertTrue(n['concurrentAllowed'])
    def test_concurrent_prohibition_retained(self):
        n=banner_expression('Course or Test: CS 201 Minimum Grade of D May not be taken concurrently.')
        self.assertFalse(n['concurrentAllowed'])
    def test_corequisite_codes(self):
        n=banner_expression('CS 204L and CS 204R');self.assertEqual(n['type'],'and')
    def test_no_field_stays_unknown(self):
        self.assertEqual(banner_expression(None)['type'],'unknown')
    def test_explicit_none(self):
        self.assertEqual(banner_expression('No prerequisites')['type'],'none')
    def test_credit_and_standing_conditions_not_dropped(self):
        for text in ['90 earned credits','Junior standing','Instructor approval','CS 201 and SAT Math 650']:
            with self.subTest(text=text):self.assertEqual(banner_expression(text)['type'],'unknown')
    def test_bad_syntax_remains_unknown(self):
        for text in ['CS 201 or','(CS 201','CS 201 CS 300','CS 201 and instructor approval']:
            with self.subTest(text=text):self.assertEqual(banner_expression(text)['type'],'unknown')

class ParserTests(unittest.TestCase):
    def test_listing_metadata_and_course_identity(self):
        d=parse_entries(f.listing(),'202601')
        self.assertEqual(set(d['courses']),{'CS 204','EE 302'})
        self.assertEqual(d['courses']['CS 204']['credits'],3)
        self.assertEqual(d['courses']['CS 204']['ects'],6)
        self.assertEqual(d['courses']['CS 204']['title'],'Test title')
    def test_catalog_listing_is_not_offering_evidence(self):
        d=parse_entries(f.listing(),'202601')
        self.assertEqual(d['availability'],'not-inferred-from-catalog')
        self.assertNotIn('offered',d['courses']['CS 204'])
    def test_missing_listing_prereqs_require_detail(self):
        d=parse_entries(f.listing(),'202601');self.assertEqual(d['details'],{})
    def test_explicit_listing_requirements_can_be_read(self):
        d=parse_entries(f.listing(cids=['CS 204'],embedded=True),'202601')
        self.assertEqual(d['details']['CS 204']['prerequisite']['code'],'CS 201')
    def test_listing_wrong_term_rejected(self):
        with self.assertRaises(CatalogError):parse_entries(f.listing(term='202602'),'202601')
    def test_wrong_link_term_rejected(self):
        html=f.listing().replace('cat_term_in=202601','cat_term_in=202602')
        with self.assertRaises(CatalogError):parse_entries(html,'202601')
    def test_no_course_results_not_saved(self):
        with self.assertRaises(CatalogError):parse_entries(f.page('Server unavailable'),'202601')
    def test_detail_preserves_each_requirement_field(self):
        d=parse_detail(f.detail(general='Junior standing'),'CS 204','202601',f.detail_url())
        self.assertEqual(d['prerequisite']['code'],'CS 201');self.assertEqual(d['corequisite']['code'],'CS 204L')
        self.assertEqual(d['generalRequirements'],'Junior standing')
    def test_absent_detail_requirement_does_not_mean_none(self):
        d=parse_detail(f.detail(prereq=None),'CS 204','202601',f.detail_url())
        self.assertEqual(d['prerequisite']['type'],'unknown')
    def test_wrong_course_response_rejected(self):
        with self.assertRaises(CatalogError):parse_detail(f.detail(cid='EE 302'),'CS 204','202601',f.detail_url())
    def test_wrong_detail_url_rejected(self):
        with self.assertRaises(CatalogError):parse_detail(f.detail(),'CS 204','202601',f.detail_url(term='202602'))
    def test_wrong_detail_term_rejected(self):
        with self.assertRaises(CatalogError):parse_detail(f.detail(term='202602'),'CS 204','202601',f.detail_url())
    def test_schedule_extracts_crns_and_meetings(self):
        d=parse_schedule(f.schedule(),'CS 204','202601',SCHEDULE_START)
        self.assertTrue(d['offered']);self.assertEqual(d['sections'][0]['crn'],'10001')
        self.assertEqual(d['sections'][0]['meetings'][0]['Instructors'],'Test instructor')
    def test_schedule_explicit_empty(self):
        self.assertFalse(parse_schedule(f.schedule(empty=True),'CS 204','202601',SCHEDULE_START)['offered'])
    def test_schedule_missing_list_stays_unknown(self):
        with self.assertRaises(CatalogError):parse_schedule(f.page('Server busy'),'CS 204','202601',SCHEDULE_START)
    def test_schedule_wrong_course_rejected(self):
        with self.assertRaises(CatalogError):parse_schedule(f.schedule(cid='EE 302'),'CS 204','202601',SCHEDULE_START)
    def test_schedule_wrong_term_rejected(self):
        with self.assertRaises(CatalogError):parse_schedule(f.schedule(term='202602'),'CS 204','202601',SCHEDULE_START)
    def test_degree_absent_category_not_fabricated(self):
        html=degree().replace('<tr><td><a href="#area">Area Electives</a></td><td>-</td><td>9</td><td>-</td></tr>','')
        a=html.index('<h2>Area Electives</h2>');b=html.index('<h2>Free Electives</h2>',a)
        d=parse_degree(html[:a]+html[b:],'BSCS','202401','https://suis.sabanciuniv.edu/prod/SU_DEGREE.p_degree_detail?P_TERM=202401&P_PROGRAM=BSCS')
        cat=next(s for s in d['sections'] if s['id']=='area')
        self.assertTrue(cat['notApplicable']);self.assertEqual(cat['courses'],[])

class AdapterTests(unittest.TestCase):
    def test_term_form_submitted_before_course_search(self):
        calls=[]
        def read(url,fields=None):
            calls.append((url,fields))
            if url==CATALOG_START:return f.selector(),url
            if url.endswith('p_disp_cat_term_date'):
                self.assertIn(('cat_term_in','202601'),fields)
                return f.search(subjects=['CS','BIO']),url
            if url==CATALOG_SEARCH:return f.listing(),url
            self.fail(url)
        result=BannerAdapter(read).catalog('202601')
        self.assertEqual(len(calls),3);self.assertEqual(result['subjects'],['CS','BIO'])
        self.assertEqual([v for k,v in calls[-1][1] if k=='sel_subj'],['dummy','CS','BIO'])
    def test_not_listed_term_stops_before_search(self):
        calls=[]
        def read(url,fields=None):calls.append(url);return f.selector(),url
        with self.assertRaises(CatalogError):BannerAdapter(read).catalog('203001')
        self.assertEqual(len(calls),1)
    def test_schedule_search_has_correct_subject_and_number(self):
        calls=[]
        def read(url,fields=None):
            calls.append((url,fields))
            if url==SCHEDULE_START:return f.selector(True),url
            if url.endswith('bwckgens.p_proc_term_date'):
                self.assertIn(('p_term','202601'),fields);return f.search(True),url
            self.assertIn(('sel_crse','204'),fields);self.assertIn(('sel_subj','CS'),fields)
            return f.schedule(),url
        d=BannerAdapter(read).schedule('CS 204','202601')
        self.assertTrue(d['offered']);self.assertEqual(len(calls),3)
    def test_multiple_schedule_types_are_all_read(self):
        links=[SCHEDULE_START.replace('p_disp_dyn_sched','p_get_crse_unsec')+'?term_in=202601&schd_in='+x for x in ['LEC','REC']]
        def read(url,fields=None):return f.schedule(crn='10001' if url.endswith('LEC') else '10002'),url
        d=BannerAdapter(read).schedule('CS 204','202601',links)
        self.assertEqual(len(d['sections']),2)

class SeparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=CatalogService(ROOT,Path(self.tmp.name)/'db.sqlite',offline=True)
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def test_term_specific_cache_never_falls_back_to_old_57_records(self):
        self.assertIsNone(self.s.fallback('course:202601:CS 204'))
        self.assertIsNotNone(self.s.fallback('course:CS 204'))
        self.assertEqual(self.s._cached_details(['CS 204'],'202601')[0],{})
    def test_different_catalog_terms_have_different_rules(self):
        for term,prereq in [('202601','CS 201'),('202602','CS 300')]:
            self.s.store.put(f'course:{term}:CS 204',{'code':'CS 204','catalogTerm':term,'prerequisite':{'type':'course','code':prereq}})
        self.assertEqual(self.s._cached_details(['CS 204'],'202601')[0]['CS 204']['prerequisite']['code'],'CS 201')
        self.assertEqual(self.s._cached_details(['CS 204'],'202602')[0]['CS 204']['prerequisite']['code'],'CS 300')
    def test_wrong_payload_term_discarded(self):
        self.s.store.put('course:202601:CS 204',{'code':'CS 204','catalogTerm':'202602'})
        self.assertEqual(self.s._cached_details(['CS 204'],'202601')[0],{})
    def test_schedule_never_creates_prerequisite_record(self):
        self.s.store.put('schedule:202601:CS 204',{'offered':True,'scheduleTerm':'202601'})
        self.assertEqual(self.s._cached_details(['CS 204'],'202601')[0],{})
    def test_bio_snapshot_is_real_partial_degree_not_ee_clone(self):
        d=self.s.fallback('degree:BSBIO:202401')
        self.assertEqual(len(next(s for s in d['sections'] if s['id']=='required')['courses']),11)
        self.assertFalse(d['complete']);self.assertTrue(all(s.get('complete') is False for s in d['sections'] if s['id'] in ['core','area','free']))
        self.assertEqual(self.s.get('degree:BSBIO:202401')['meta']['state'],'partial')
    def test_catalog_term_and_admission_term_independent_api(self):
        self.s.store.put('course:202601:CS 204',{'code':'CS 204','catalogTerm':'202601','origin':'live'})
        status,_,d=service_helpers.ServiceTests.call(App(service=self.s),'/api/course',query='code=CS%20204&catalogTerm=202601')
        self.assertEqual(status,'200 OK');self.assertEqual(d['data']['catalogTerm'],'202601')
    def test_invalid_new_api_queries_rejected(self):
        a=App(service=self.s)
        for path,q in [('/api/catalog','catalogTerm=no'),('/api/schedule','term=202601&code=../../'),('/api/course','code=CS204&catalogTerm=202601&url=x')]:
            with self.subTest(q=q):self.assertEqual(service_helpers.ServiceTests.call(a,path,query=q)[0],'400 Bad Request')
    def test_all_12_major_routes_keep_requested_identity(self):
        # Synthetic degree fixtures verify generic routing, NOT 12 live data sets.
        self.s.seed['degrees'] = {}
        for program in PROGRAM_MAP:
            observed=[]
            class Client:
                offline=False
                def get(_,url):
                    op,q=catalog_link(url);observed.append((op,q))
                    if op=='su_degree.p_degree_detail':return degree(program),url
                    if op=='su_degree.p_list_courses':return pool(program),url
                    raise AssertionError(url)
            self.s.client=Client()
            d=self.s.load(f'degree:{program}:202401')
            self.assertEqual(d['program']['id'],program);self.assertTrue(d['complete'])
            self.assertTrue(all(q['P_PROGRAM']==[program] for _,q in observed))
    def test_unavailable_major_never_substitutes_ee(self):
        self.assertIsNone(self.s.get('degree:BSCS:202401')['data'])
    def test_load_lock_memory_is_bounded(self):
        self.assertEqual(len(self.s._load_locks),64)

if __name__=='__main__':unittest.main()
