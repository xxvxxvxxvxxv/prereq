#!/usr/bin/env python3
"""Exercise the real app, service, parser, API and browser over loopback HTTP.
The upstream client is a deterministic fixture, NOT a university connection.
Chromium navigation to localhost is restricted in this environment. An explicit
test binding calls the WSGI app; no browser/admin policy is modified.
Never deploy this harness. It is not part of the production entry point.
"""
import argparse,json,sys,tempfile,threading,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from wsgiref.simple_server import make_server,WSGIRequestHandler,WSGIServer
from socketserver import ThreadingMixIn
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from prereq.app import App
from prereq.service import CatalogService
from prereq.catalog import catalog_link,code
from prereq.banner import CATALOG_START,CATALOG_SEARCH,SCHEDULE_START
from tests import banner_fixtures as f
from tests.fixtures import degree,pool,row
from playwright.sync_api import sync_playwright

class FixtureClient:
    offline=False
    def __init__(self):self.calls=[]
    def get(self,url):return self.read(url)
    def post(self,url,fields):return self.read(url,fields)
    def read(self,url,fields=None):
        self.calls.append((url,fields));op,q=catalog_link(url)
        if op=='su_degree.p_degree_detail':return degree(program=q['P_PROGRAM'][0]),url
        if op=='su_degree.p_list_courses':
            area=q['P_AREA'][0]
            if area.endswith('CUSTOM1'):
                return pool(cid='CS 201').replace('</table>',row('CS 204','Advanced Programming')+'</table>'),url
            return pool(cid='CS 300' if area.endswith('AEL') else 'ECON 201'),url
        if url==CATALOG_START:return f.selector(),url
        if url==SCHEDULE_START:return f.selector(True),url
        if url.endswith('p_disp_cat_term_date'):return f.search(),url
        if url==CATALOG_SEARCH:
            # The fixture supports both broad and exact queries. The live app
            # must use exact queries for its first prerequisite records.
            q=parse_qs(__import__('urllib.parse',fromlist=['urlencode']).urlencode(fields or []),keep_blank_values=True)
            selected=[x for x in q.get('sel_subj',[]) if x!='dummy']
            if len(selected)==1 and q.get('sel_crse_strt',[''])[0]:
                return f.listing([code(selected[0]+q['sel_crse_strt'][0])],q['term_in'][0]),url
            return f.listing(['CS 201','CS 204','CS 300','CS 303','ECON 201','MATH 101']),url
        if url.endswith('bwckgens.p_proc_term_date'):return f.search(True),url
        if url.endswith('bwckschd.p_get_crse_unsec'):return f.schedule(),url
        if 'bwckctlg.p_disp_course_detail' in url:
            q=parse_qs(urlsplit(url).query);cid=code(q['subj_code_in'][0]+q['crse_numb_in'][0])
            parent={'CS 201':'MATH 101','CS 204':'CS 201','CS 300':'CS 204','CS 303':'CS 201'}.get(cid)
            expr=('Undergraduate level '+parent+' Minimum Grade of D') if parent else 'None'
            return f.detail(cid=cid,prereq=expr,coreq='CS 204L' if cid=='CS 204' else 'None'),url
        raise AssertionError('Unexpected fixture URL: '+url)
class Server(ThreadingMixIn,WSGIServer):daemon_threads=True
class Quiet(WSGIRequestHandler):
    def log_message(self,*args):pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chromium',default='/usr/bin/chromium');parser.add_argument('--report',type=Path);args=parser.parse_args()
    checks=[]
    def check(name,value):
        assert value,name
        checks.append(name);print('PASS',name,flush=True)
    with tempfile.TemporaryDirectory() as temp:
        client=FixtureClient();service=CatalogService(root,Path(temp)/'catalog.sqlite3',client=client)
        app=App(service=service);server=make_server('127.0.0.1',0,app,server_class=Server,handler_class=Quiet)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=args.chromium,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1365,'height':900});page.set_default_timeout(18000)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                # Run in about:blank and bridge test requests to the actual WSGI app.
                def fetch_bridge(path,opts=None):
                    from urllib.parse import urlsplit
                    opts=opts or {};u=urlsplit(path);response={}
                    env={'REQUEST_METHOD':opts.get('method','GET'),'PATH_INFO':'/'+u.path.lstrip('/'),
                         'QUERY_STRING':u.query,'HTTP_HOST':'127.0.0.1:8765','REMOTE_ADDR':'127.0.0.1',
                         'HTTP_X_PREREQ_CLIENT':'1','CONTENT_LENGTH':'0','wsgi.url_scheme':'http'}
                    def start(status,headers):response.update(status=int(status.split()[0]),headers=dict(headers))
                    body=b''.join(app(env,start));response['body']=body.decode('utf-8');return response
                page.expose_function('__testFetch',fetch_bridge)
                html=(root/'preview.html').read_text().replace('window.__PREVIEW_SEED__=','window.__FIXTURE_SEED__=')
                boot="""<script>window.__storage=new Map();Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>__storage.get(k)||null,setItem:(k,v)=>__storage.set(k,String(v)),removeItem:k=>__storage.delete(k)}});window.fetch=async (url,options={})=>{const r=await window.__testFetch(String(url),{method:options.method||'GET'});return new Response(r.body,{status:r.status,headers:r.headers});};</script>"""
                html=html.replace('<head>','<head>'+boot,1)
                page.set_content(html,wait_until='load')
                page.locator('#major-select').select_option('BSCS');page.locator('#open-map').click()
                page.wait_for_function("document.querySelector('[data-node=\"section:required\"]')!==null")
                check('Non-EE selection loads its own parsed degree through actual API',page.locator('#selected-major').inner_text()=='Computer Science and Engineering')
                check('Admission year stays 2024 while catalog term is 202601','2024' in page.locator('#selected-term').inner_text() and page.locator('#catalog-term').input_value()=='202601')
                check('All five sections initially closed',page.locator('[data-node][aria-expanded="false"]').count()==5)
                page.wait_for_function("document.getElementById('match-count').textContent.startsWith('6/6')",timeout=20000)
                check('Background catalog/details use actual service and parser',any(fields is not None and url==CATALOG_SEARCH for url,fields in client.calls))
                cam=page.locator('#viewport').get_attribute('transform')
                page.locator('[data-node="section:core"]').dispatch_event('click');page.wait_for_timeout(380)
                page.locator('[data-node="section:core/CS 201"]').dispatch_event('click');page.wait_for_timeout(380)
                check('Parsed Banner relationship creates a CS201 to CS204 edge',page.locator('[data-node="section:core/CS 201>CS 204"]').count()==1)
                check('Newly loaded prerequisite expansion preserves camera',page.locator('#viewport').get_attribute('transform')==cam)
                page.locator('[data-node="section:core/CS 201>CS 204"] [data-action="info"]').click()
                page.wait_for_function("document.querySelector('#course-content .requirement-expression')?.textContent.includes('CS 201')")
                check('Detail pane retains minimum grade and separate laboratory','min D' in page.locator('#course-content').inner_text() and 'CS 204L' in page.locator('#course-content').inner_text())
                page.get_by_role('button',name='◇ Planned',exact=True).click()
                check('Local plan can be edited without sending markers upstream',page.locator('#plan-count').inner_text()=='1' and all(not fields or not any(k=='marks' for k,v in fields) for _,fields in client.calls))
                page.get_by_role('button',name='Check sections',exact=True).click()
                page.wait_for_function("document.querySelector('#course-content')?.textContent.includes('10001')")
                check('Dynamic Schedule is read separately and displays CRN plus instructor','Test instructor' in page.locator('#course-content').inner_text())
                check('Prerequisite cache and schedule cache have separate keys',service.store.get('course:202601:CS 204')[0]['catalogTerm']=='202601' and service.store.get('schedule:202601:CS 204')[0]['scheduleTerm']=='202601')
                page.locator('#close-course').click();page.locator('#reset-button').click();page.wait_for_timeout(380)
                check('Reset closes everything but keeps the plan',page.locator('[data-node]').count()==5 and page.locator('#plan-count').inner_text()=='1')
                saved=page.evaluate('Object.fromEntries(__storage)');reload_html=html.replace('window.__storage=new Map();','window.__storage=new Map('+json.dumps(list(saved.items()))+');');page.set_content(reload_html,wait_until='load');page.wait_for_function("document.querySelector('[data-node=\"section:core\"]')!==null")
                check('Simulated persisted browser storage restores plan',page.locator('#plan-count').inner_text()=='1')
                check('Reload leaves every section closed',page.locator('[data-node][aria-expanded="false"]').count()==5)
                page.locator('#catalog-term').select_option('202602');page.wait_for_timeout(100)
                check('Changing catalog semester immediately clears earlier-term edges',page.locator('#match-count').inner_text().startswith('0/'))
                check('Changing catalog semester does not change admission or saved plan','2024' in page.locator('#selected-term').inner_text() and page.locator('#plan-count').inner_text()=='1')
                print('JS errors:',errors,flush=True);check('Frontend completes integration test without JavaScript exceptions',not errors)
                browser.close()
        finally:
            server.shutdown();server.server_close();worker.join();service.close()
    report={'passed':len(checks),'checks':checks,'scope':'Chromium uses an explicit test binding to the real WSGI app, service and parsers with synthetic upstream responses. Saved browser storage is simulated. Separate HTTP smoke checks use loopback sockets. NOT a live university, real browser-network or real storage persistence test.'}
    print(json.dumps(report,indent=2))
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
