import unittest
from prereq.catalog import *
from tests.fixtures import degree,pool,row,course,terms,pool_url

class CatalogTests(unittest.TestCase):
    def test_code_normalization_and_special_topics(self):
        self.assertEqual(code('ee48012'),'EE 48012')
        self.assertEqual(code('CIP101N'),'CIP 101N')
        self.assertEqual(code('ee202r'),'EE 202R')
    def test_bad_codes(self):
        for bad in ('http://localhost','EE 202;DROP TABLE','<script>','EE','EE202123'):
            with self.assertRaises(CatalogError): code(bad)
    def test_terms_from_select_and_anchors(self):
        self.assertEqual(parse_terms(terms(),'BSCS')[0]['id'],'202401')
    def test_terms_missing(self):
        with self.assertRaises(CatalogError): parse_terms('<p>Sign in</p>','BSEE')
    def test_degree_structure(self):
        result=parse_degree(degree(),'BSCS','202401',degree_url('BSCS','202401'))
        self.assertEqual(result['total']['credits'],125)
        self.assertEqual(result['total']['ects'],240)
        self.assertEqual(len(result['sections']),5)
        self.assertEqual(result['sections'][0]['courses'][0]['code'],'MATH 101')
        self.assertIn('review choices',result['sections'][0]['rule'])
        self.assertEqual(result['poolLinks']['area'],pool_url('BSCS','202401','area'))
    def test_wrong_program_rejected(self):
        with self.assertRaises(CatalogError): parse_degree(degree(),'BSEE','202401',degree_url('BSEE','202401'))
    def test_wrong_admission_rejected(self):
        with self.assertRaises(CatalogError): parse_degree(degree(),'BSCS','202601',degree_url('BSCS','202601'))
    def test_missing_section_rejected(self):
        with self.assertRaises(CatalogError): parse_degree(degree().replace('<h2>Free Electives</h2>','<h2>Changed</h2>'),'BSCS','202401',degree_url('BSCS','202401'))
    def test_wrong_term_pool_link_rejected(self):
        html=degree().replace('P_TERM=202401','P_TERM=202601')
        with self.assertRaises(CatalogError): parse_degree(html,'BSCS','202401',degree_url('BSCS','202401'))
    def test_course_rows_without_official_links_are_rejected(self):
        html=pool().replace('sabanci_www.p_get_courses','changed_endpoint')
        with self.assertRaises(CatalogError): parse_pool(html,'BSCS',pool_url('BSCS','202401','core'))
    def test_pool_numbers(self):
        result=parse_pool(pool(),'BSCS',pool_url('BSCS','202401','core'))
        self.assertEqual(result[0]['credits'],3)
        self.assertEqual(result[0]['ects'],6)
        self.assertTrue(result[0]['facultyCourse'])
    def test_pool_empty_or_wrong_identity(self):
        for html in ('<h1>(BSCS)</h1>',pool('BSEE')):
            with self.assertRaises(CatalogError): parse_pool(html,'BSCS',pool_url('BSCS','202401','core'))
    def test_malformed_course_row_fails_closed(self):
        html=pool().replace('<td>6</td>','<td>?</td>')
        with self.assertRaises(CatalogError): parse_pool(html,'BSCS',pool_url('BSCS','202401','core'))
    def test_zero_credits_not_missing(self):
        html='<h1>(BSCS)</h1><table>'+row('EE 395','Internship',5,0)+'</table>'
        self.assertEqual(parse_pool(html,'BSCS',pool_url('BSCS','202401','core'))[0]['credits'],0)
    def test_nested_wrapper_tables_do_not_duplicate(self):
        html='<table><tr><td>'+pool()+'</td></tr></table>'
        self.assertEqual(len(parse_pool(html,'BSCS',pool_url('BSCS','202401','core'))),1)
    def test_explicit_none_vs_missing(self):
        self.assertEqual(parse_expression('__')['type'],'none')
        self.assertEqual(parse_expression('')['type'],'unknown')
        self.assertEqual(parse_expression(None)['type'],'unknown')
    def test_parentheses_and_grades(self):
        x=parse_expression('(MATH 201 - Undergraduate - Min Grade D and MATH 202 - Undergraduate - Min Grade C) or MATH 212 - Undergraduate - Min Grade D')
        self.assertEqual(x['type'],'or');self.assertEqual(x['children'][0]['type'],'and')
        self.assertEqual(x['children'][0]['children'][1]['minGrade'],'C')
    def test_and_binds_more_tightly_than_or(self):
        x=parse_expression('CS 201 or CS 204 and CS 300')
        self.assertEqual(x['children'][1]['type'],'and')
    def test_unknown_prose_not_ignored(self):
        for raw in ('EE 202 and instructor consent','CS 201 CS 204','(EE 202','EE 202 or'):
            self.assertEqual(parse_expression(raw)['type'],'unknown')
    def test_actual_detail_layout(self):
        x=parse_course(course(),'EE 202',course_url('EE 202'))
        self.assertEqual(x['prerequisite']['code'],'ENS 203')
        self.assertEqual(x['corequisite']['type'],'and')
        self.assertEqual(x['corequisite']['children'][1]['code'],'EE 202R')
        self.assertEqual(x['ects'],6)
    def test_missing_requirement_is_failure(self):
        with self.assertRaises(CatalogError): parse_course(course().replace('Prerequisite:','Prior knowledge:'),'EE 202',course_url('EE 202'))
    def test_html_scripts_not_interpreted(self):
        d=Document('<p>Safe text</p><script>window.stolen=1</script><style>evil</style>')
        self.assertEqual(d.text,'Safe text')
    def test_expression_complexity_limit(self):
        self.assertEqual(parse_expression('('*200+'EE 202'+')'*200)['type'],'unknown')

if __name__=='__main__': unittest.main()
