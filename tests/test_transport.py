"""Deterministic transport tests. No university network or real cookies used."""
import io
import socket
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.parse import parse_qs
from prereq.network import OfficialClient,validate_url,MAX_BODY
from prereq.catalog import CatalogError
from prereq.banner import CATALOG_SEARCH,CATALOG_START,catalog_form,CAPTURED_SUBJECTS

class Response:
    def __init__(self,body=b'<html>test</html>',status=200,headers=None):
        self.status=status;self.body=io.BytesIO(body);self.headers=Message()
        for k,v in (headers or {'Content-Type':'text/html; charset=utf-8'}).items():self.headers[k]=v
    def getheader(self,key,default=None):return self.headers.get(key,default)
    def getheaders(self):return list(self.headers.items())
    def read(self,n):return self.body.read(n)

class Conn:
    calls=[];responses=[];created=[]
    def __init__(self,host,timeout,context):
        self.host=host;self.timeout=timeout;self.sock=None;self.closed=False;Conn.created.append(self)
    def request(self,method,path,body=None,headers=None):
        Conn.calls.append(dict(host=self.host,timeout=self.timeout,method=method,path=path,body=body,headers=headers))
    def getresponse(self):return Conn.responses.pop(0)
    def close(self):self.closed=True

class TransportTests(unittest.TestCase):
    def setUp(self):
        Conn.calls=[];Conn.created=[];Conn.responses=[]
        self.connpatch=patch('prereq.network.PinnedHTTPS',Conn);self.connpatch.start()
        self.pause=patch('prereq.network.time.sleep');self.pause.start()
    def tearDown(self):self.connpatch.stop();self.pause.stop()
    def test_exact_post_body_and_content_type(self):
        Conn.responses=[Response()];client=OfficialClient()
        client.post(CATALOG_SEARCH,catalog_form('202601',CAPTURED_SUBJECTS))
        r=Conn.calls[0]
        self.assertEqual(r['method'],'POST');self.assertEqual(len(r['body']),1267)
        self.assertEqual(r['headers']['Content-Type'],'application/x-www-form-urlencoded')
        self.assertEqual(len(parse_qs(r['body'].decode())['sel_subj']),75)
    def test_timeout_allows_more_than_10_seconds(self):
        Conn.responses=[Response()];OfficialClient().get(CATALOG_START)
        self.assertGreaterEqual(Conn.created[0].timeout,45)
    def test_4mb_response_is_not_rejected_by_old_2mb_cap(self):
        body=b'<html>'+b'X'*4_100_000+b'</html>';Conn.responses=[Response(body)]
        html,url=OfficialClient().get(CATALOG_START);self.assertEqual(len(html),len(body))
    def test_oversize_content_length_stops_before_read(self):
        Conn.responses=[Response(headers={'Content-Type':'text/html','Content-Length':str(MAX_BODY+1)})]
        with self.assertRaises(CatalogError):OfficialClient().get(CATALOG_START)
        self.assertTrue(Conn.created[0].closed)
    def test_oversize_chunked_body_stops(self):
        Conn.responses=[Response(b'x'*(MAX_BODY+1))]
        with self.assertRaises(CatalogError):OfficialClient().get(CATALOG_START)
    def test_network_connections_are_closed(self):
        Conn.responses=[Response()];OfficialClient().get(CATALOG_START)
        self.assertTrue(all(c.closed for c in Conn.created))
    def test_public_query_mode_does_not_mislabel_robots_as_http_failure(self):
        Conn.responses=[Response()];OfficialClient(policy='public-queries').get(CATALOG_START)
        self.assertEqual([x['path'] for x in Conn.calls],['/prod/bwckctlg.p_disp_dyn_ctlg'])
    def test_robots_opt_in_remains_available(self):
        Conn.responses=[Response(b'User-agent: *\nDisallow: /')]
        with self.assertRaises(CatalogError):OfficialClient(policy='robots').get(CATALOG_START)
        self.assertEqual(len(Conn.calls),1);self.assertEqual(Conn.calls[0]['path'],'/robots.txt')
    def test_real_access_refusals_always_stop(self):
        for status in (401,403,429,503):
            with self.subTest(status=status):
                Conn.calls=[];Conn.responses=[Response(status=status,headers={'Retry-After':'120'})];c=OfficialClient()
                with self.assertRaisesRegex(CatalogError,'HTTP '+str(status)):c.get(CATALOG_START)
                with self.assertRaisesRegex(CatalogError,'cooldown'):c.get(CATALOG_START)
                self.assertEqual(len(Conn.calls),1)
    def test_challenge_and_sign_in_pages_stop(self):
        for body in [b'<input type="password">',b'<div class="g-recaptcha">',b'<script src="/cf-chl-x">']:
            Conn.responses=[Response(body)]
            with self.subTest(body=body),self.assertRaises(CatalogError):OfficialClient().get(CATALOG_START)
    def test_redirect_to_login_is_not_followed(self):
        Conn.responses=[Response(status=302,headers={'Location':'https://suis.sabanciuniv.edu/prod/twbkwbis.P_WWWLogin'})]
        with self.assertRaises(CatalogError):OfficialClient().get(CATALOG_START)
        self.assertEqual(len(Conn.calls),1)
    def test_post_does_not_redirect_to_another_host(self):
        target='https://www.sabanciuniv.edu/en/prospective-students/degree-detail?SU_DEGREE.p_degree_detail?P_TERM=202401&P_PROGRAM=BSBIO'
        Conn.responses=[Response(status=307,headers={'Location':target})]
        with self.assertRaises(CatalogError):OfficialClient().post(CATALOG_SEARCH,catalog_form('202601',['CS']))
    def test_303_after_post_becomes_get(self):
        Conn.responses=[Response(status=303,headers={'Location':CATALOG_START}),Response()]
        OfficialClient().post(CATALOG_SEARCH,catalog_form('202601',['CS']))
        self.assertEqual([r['method'] for r in Conn.calls],['POST','GET']);self.assertIsNone(Conn.calls[1]['body'])
    def test_anonymous_cookie_jar_not_shared_between_clients(self):
        Conn.responses=[Response(headers={'Content-Type':'text/html','Set-Cookie':'TEST_SESSION=fixture; Secure'}),Response(),Response()]
        c=OfficialClient();c.get(CATALOG_START);c.get(CATALOG_START);OfficialClient().get(CATALOG_START)
        self.assertNotIn('Cookie',Conn.calls[0]['headers']);self.assertIn('TEST_SESSION',Conn.calls[1]['headers']['Cookie'])
        self.assertNotIn('Cookie',Conn.calls[2]['headers'])
    def test_invalid_fetch_policy_rejected(self):
        with self.assertRaises(ValueError):OfficialClient(policy='bypass')
    def test_wrapped_degree_url_preserves_both_question_marks(self):
        url='https://www.sabanciuniv.edu/en/prospective-students/degree-detail?SU_DEGREE.p_degree_detail?P_TERM=202401&P_PROGRAM=BSBIO&P_SUBMIT=&P_LANG=EN&P_LEVEL=UG'
        self.assertEqual(validate_url(url),url)
        Conn.responses=[Response()];OfficialClient().get(url)
        self.assertIn('?SU_DEGREE.p_degree_detail?P_TERM=202401&P_PROGRAM=BSBIO',Conn.calls[0]['path'])
    def test_other_hosts_and_registration_writes_are_rejected(self):
        for url in ['https://example.org/robots.txt','https://suis.sabanciuniv.edu/prod/bwskfreg.P_AltPin','https://localhost/robots.txt','https://suis.sabanciuniv.edu/prod/bwckctlg.p_disp_dyn_ctlg?url=bad']:
            with self.subTest(url=url),self.assertRaises(CatalogError):OfficialClient().get(url)
        self.assertEqual(Conn.calls,[])
    def test_post_to_detail_not_allowed(self):
        from tests.banner_fixtures import detail_url
        with self.assertRaises(CatalogError):OfficialClient().post(detail_url(),[])
        self.assertEqual(Conn.calls,[])
    def test_wrong_content_type_not_parsed(self):
        Conn.responses=[Response(headers={'Content-Type':'application/octet-stream'})]
        with self.assertRaises(CatalogError):OfficialClient().get(CATALOG_START)
    def test_client_form_rejects_unknown_fields(self):
        with self.assertRaises(CatalogError):OfficialClient().post(CATALOG_SEARCH,[('password','secret')])
        self.assertEqual(Conn.calls,[])
    def test_selector_p_term_and_calling_proc_are_supported(self):
        Conn.responses=[Response()]
        OfficialClient().post('https://suis.sabanciuniv.edu/prod/bwckgens.p_proc_term_date',[
            ('p_term','202601'),('p_calling_proc','bwckschd.p_disp_dyn_sched')])
        self.assertEqual(len(Conn.calls),1)
    def test_binary_body_without_length_remains_bounded(self):
        Conn.responses=[Response(b'test',headers={'Content-Type':'text/html','Content-Encoding':'gzip'})]
        with self.assertRaises(CatalogError):OfficialClient().get(CATALOG_START)

if __name__=='__main__':unittest.main()
