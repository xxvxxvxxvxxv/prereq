"""Regressions based on the user's actual saved degree HTML, not guessed rows."""
import unittest
from pathlib import Path
from prereq.catalog import CatalogError, catalog_link, parse_degree, parse_terms
from prereq.degree_snapshot import extract_degree_snapshot

SOURCE = ('https://www.sabanciuniv.edu/en/prospective-students/degree-detail?'
          'SU_DEGREE.p_degree_detail?P_TERM=202401&P_PROGRAM=BSBIO&'
          'P_SUBMIT=&P_LANG=EN&P_LEVEL=UG')
HTML = (Path(__file__).parent/'fixtures_html/bsbio-202401-degree.html').read_text(encoding='utf-8')


class DegreeWrapperTests(unittest.TestCase):
    def data(self, html=HTML):
        return parse_degree(html, 'BSBIO', '202401', SOURCE)

    def test_actual_page_extracts_embedded_course_counts(self):
        sections = self.data()['sections']
        self.assertEqual([len(s['courses']) for s in sections[:2]], [24, 11])
        self.assertEqual(sum(c['credits'] for c in sections[1]['courses']), 33)

    def test_three_real_pool_links_not_invented_suffixes(self):
        pools = self.data()['poolLinks']
        self.assertEqual(set(pools), {'core', 'area', 'free'})
        for key, suffix in [('core', 'CEL'), ('area', 'AEL'), ('free', 'FEL')]:
            operation, params = catalog_link(pools[key])
            self.assertEqual(operation, 'su_degree.p_list_courses')
            self.assertEqual(params['P_AREA'], ['BSBIO_' + suffix])
            self.assertEqual(params['P_TERM'], ['202401'])

    def test_nested_query_restores_first_parameter(self):
        operation, p = catalog_link(SOURCE)
        self.assertEqual(operation, 'su_degree.p_degree_detail')
        self.assertEqual(p['P_TERM'], ['202401'])
        self.assertEqual(p['P_SUBMIT'], [''])

    def test_encoded_nested_delimiter(self):
        source = SOURCE.replace('p_degree_detail?P_TERM', 'p_degree_detail%3FP_TERM')
        self.assertEqual(catalog_link(source)[1]['P_TERM'], ['202401'])

    def test_original_course_links_preserved(self):
        rows = self.data()['sections'][1]['courses']
        self.assertEqual(rows[0]['code'], 'BIO 301')
        self.assertTrue(rows[0]['source'].startswith('https://www.sabanciuniv.edu/'))
        self.assertIn('subj_code=BIO&crse_numb=301', rows[0]['source'])

    def test_zero_credit_internship_and_faculty_marks(self):
        courses = {c['code']: c for s in self.data()['sections'] for c in s['courses']}
        self.assertEqual(courses['BIO 395']['credits'], 0)
        self.assertTrue(courses['NS 201']['facultyCourse'])
        self.assertFalse(courses['BIO 301']['facultyCourse'])

    def test_real_summary(self):
        data = self.data()
        self.assertEqual(data['total']['credits'], 127)
        self.assertEqual(data['total']['ects'], 240)
        summary = {r['label']: r for r in data['summary']}
        self.assertEqual(summary['Core Electives']['credits'], 29)
        self.assertEqual(summary['Required Courses']['courses'], 11)

    def test_university_options_not_all_mandatory(self):
        rule = self.data()['sections'][0]['rule']
        self.assertIn('16 courses and 41 SU credits', rule)
        self.assertIn('One of the HUM', rule)

    def test_wrong_major_rejected(self):
        with self.assertRaises(CatalogError):
            parse_degree(HTML, 'BSEE', '202401', SOURCE)

    def test_wrong_cohort_rejected(self):
        with self.assertRaises(CatalogError):
            parse_degree(HTML, 'BSBIO', '202601', SOURCE)

    def test_cross_cohort_elective_link_rejected(self):
        bad = HTML.replace('p_list_courses?P_TERM=202401', 'p_list_courses?P_TERM=202601')
        with self.assertRaises(CatalogError):
            self.data(bad)

    def test_footer_not_included_in_degree_rules(self):
        data = self.data(HTML + '<footer><p>FOOTER_MARKER</p></footer>')
        self.assertFalse(any('FOOTER_MARKER' in n['text'] for n in data['notes']))

    def test_duplicate_parameters_rejected(self):
        with self.assertRaises(CatalogError):
            catalog_link(SOURCE + '&P_TERM=202601')

    def test_non_official_course_link_rejected(self):
        bad = HTML.replace('/en/prospective-students/degree-detail?',
                           'https://attacker.invalid/en/prospective-students/degree-detail?')
        with self.assertRaises(CatalogError):
            self.data(bad)

    def test_credential_and_port_links_rejected(self):
        for url in (SOURCE.replace('https://', 'https://user:pass@'),
                    SOURCE.replace('.edu/', '.edu:8443/')):
            self.assertEqual(catalog_link(url), ('', {}))

    def test_terms_from_wrapper_anchor(self):
        self.assertEqual(parse_terms(f'<a href="{SOURCE}">Fall</a>', 'BSBIO')[0]['id'], '202401')

    def test_incomplete_pool_is_unknown_not_empty(self):
        data = extract_degree_snapshot(HTML, SOURCE)
        self.assertFalse(data['degreePoolsComplete'])
        for s in data['sections'][2:]:
            self.assertFalse(s['complete'])
            self.assertIsNone(s['totalCourseOptions'])

    def test_no_offerings_or_prerequisites_inferred(self):
        data = extract_degree_snapshot(HTML, SOURCE)
        self.assertIsNone(data['catalogTerm'])
        self.assertEqual(data['admissionTerm'], '202401')
        self.assertEqual(data['availability']['status'], 'not-provided')
        self.assertEqual(data['prerequisiteData']['status'], 'not-provided')
        self.assertIsNone(data['observedAt'])


if __name__ == '__main__':
    unittest.main()
