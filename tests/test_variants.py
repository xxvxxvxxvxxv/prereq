"""Reconstructed cases based on observed PSY, VACD and Management structures."""
import unittest
from prereq.catalog import parse_degree, degree_url, parse_pool, CatalogError
from tests.fixtures import degree,row,pool_url
from html import escape

class VariantTests(unittest.TestCase):
    def parse(self, html, program='BSCS'):
        return parse_degree(html,program,'202401',degree_url(program,'202401'))
    def test_free_elective_singular(self):
        result=self.parse(degree().replace('Free Electives','Free Elective'))
        self.assertEqual(result['sections'][4]['id'],'free')
    def test_philosophy_kept_separate_from_required(self):
        html=degree('BAPSY')
        html=html.replace('<tr><td>Total</td>', '<tr><td>Philosophy Requirement Course</td><td>-</td><td>3</td><td>1</td></tr><tr><td>Total</td>')
        html=html.replace('<h2>Core Electives</h2>', '<h2>Philosophy Requirement Course</h2><p>Either PHIL 300 or PHIL 301.</p><table>'+row('PHIL 300','Philosophy of Science',6,3,'FASS')+row('PHIL 301','Political Philosophy',6,3,'FASS')+'</table><h2>Core Electives</h2>')
        result=self.parse(html,'BAPSY')
        extra=[s for s in result['sections'] if s.get('category')=='additional'][0]
        self.assertEqual([c['code'] for c in extra['courses']],['PHIL 300','PHIL 301'])
        self.assertNotIn('PHIL 300',[c['code'] for c in result['sections'][1]['courses']])
        self.assertIn('Either',extra['rule'])
    def test_split_core_requirements_preserve_two_minima(self):
        html=degree('BAVACD').replace('Core Electives','Core Electives I (Art/Design History Courses)')
        html=html.replace('<tr><td>Total</td>', '<tr><td>Core Electives II (Skill Courses)</td><td>-</td><td>12</td><td>-</td></tr><tr><td>Total</td>')
        html=html.replace('<h2>Area Electives</h2>', '<h2>Core Electives II (Skill Courses)</h2><p>Choose 12 SU credits. VA 302 or VA 304.</p><table>'+row('VA 302','Art Studio II',7,3,'FASS')+row('VA 304','Design Studio II',7,3,'FASS')+'</table><h2>Area Electives</h2>')
        core=self.parse(html,'BAVACD')['sections'][2]
        self.assertEqual(core['id'],'core')
        self.assertEqual(len(core['subsections']),2)
        self.assertEqual(core['subsections'][1]['minimum']['credits'],12)
        self.assertIn('VA 302 or VA 304',core['subsections'][1]['rule'])
    def test_unknown_summary_section_not_silently_dropped(self):
        html=degree().replace('<tr><td>Total</td>', '<tr><td>New Requirement</td><td>-</td><td>3</td><td>1</td></tr><tr><td>Total</td>')
        with self.assertRaises(CatalogError):self.parse(html)
    def test_management_term_and_detail_routes_differ(self):
        self.assertIn('/HbbmInst/',degree_url('BAMAN'))
        self.assertIn('/prod/',degree_url('BAMAN','202401'))
    def test_bio_heading_whitespace(self):
        self.assertEqual(self.parse(degree('BSBIO').replace('(BSBIO)','(BSBIO )'),'BSBIO')['program']['id'],'BSBIO')
