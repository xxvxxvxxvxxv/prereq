#!/usr/bin/env python3
"""Real Chromium tests of the offline build. No upstream network access.
The about:blank harness simulates localStorage, not browser disk persistence.
Animation checks sample actual DOM position, opacity and viewport transforms.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--chromium',help='Path to a system Chromium executable')
parser.add_argument('--screenshots',type=Path)
args=parser.parse_args()
html=(ROOT/'preview.html').read_text(encoding='utf-8')
bootstrap='''<script>(()=>{const m=new Map();Object.defineProperty(window,'localStorage',{configurable:true,value:{getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,String(v)),removeItem:k=>m.delete(k),clear:()=>m.clear()}});})();</script>'''
html=html.replace('<head>','<head>'+bootstrap,1)
checks=[]
def check(name,value):
    assert value,name
    checks.append(name);print('PASS',name,flush=True)
def shot(page,name):
    if args.screenshots:
        args.screenshots.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(args.screenshots/(name+'.png')))
def camera(page):return page.locator('#viewport').get_attribute('transform')
def choose(page):
    page.set_content(html,wait_until='load');page.locator('#open-map').click();page.wait_for_timeout(450)
def find(page,code):
    page.locator('#search').fill(code);page.locator('#search-results button').first.click();page.wait_for_timeout(450)
def detail(page,code):
    find(page,code);code=re.sub(r"([A-Z])(?=\d)", r"\1 ", code);page.locator(f'[data-node="focus:{code}"] [data-action="info"]').click()
def toggle_frames(page,id,child):
    return page.evaluate('''async ({id,child})=>{
      const q=x=>document.querySelector('[data-node="'+x+'"]');
      const vp=document.getElementById('viewport'),parent=q(id),before=vp.getAttribute('transform'),anchor=parent.getAttribute('transform');
      parent.dispatchEvent(new MouseEvent('click',{bubbles:true}));
      const immediate={present:!!q(child),animating:vp.dataset.animating};
      const frames=[],start=performance.now();
      await new Promise(resolve=>{function tick(t){const c=q(child);frames.push({t:t-start,camera:vp.getAttribute('transform'),parent:parent.getAttribute('transform'),present:!!c,opacity:c?Number(c.getAttribute('opacity')):null,pos:c?.getAttribute('transform')});if(t-start<430)requestAnimationFrame(tick);else resolve();}requestAnimationFrame(tick);});
      return {before,anchor,immediate,frames};
    }''',dict(id=id,child=child))

with sync_playwright() as p:
    opts=dict(headless=True,args=['--no-sandbox'])
    if args.chromium:opts['executable_path']=args.chromium
    browser=p.chromium.launch(**opts)
    page=browser.new_page(viewport={'width':1440,'height':960},accept_downloads=True)
    page.set_default_timeout(5000);errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(html,wait_until='load')
    check('Major chooser opens',page.locator('#chooser').get_attribute('open') is not None)
    shot(page,'chooser');page.locator('#open-map').click();page.wait_for_timeout(450)
    check('No marketing headline or tinted background',not page.locator('.map-heading').count() and page.evaluate("getComputedStyle(document.body).backgroundColor==='rgb(0, 0, 0)'"))
    check('All graph text is white',page.locator('#viewport text').evaluate_all("xs=>xs.every(x=>getComputedStyle(x).fill==='rgb(255, 255, 255)')"))
    check('Subject colors affect dots rather than labels',page.locator('.dot.subject-cs').first.evaluate("e=>getComputedStyle(e).fill==='rgb(255, 102, 102)'"))
    check('University courses start open, major-required follows, electives start closed',page.locator('[data-node="section:university"]').get_attribute('aria-expanded')=='true' and page.locator('[data-node="section:required"]').get_attribute('aria-expanded')=='true' and page.locator('[data-node="section:area"]').get_attribute('aria-expanded')=='false')
    check('Actual IF 100 to CS 201 to CS 204 path rendered',page.locator('[data-node="section:university/IF 100>CS 201>CS 204"]').count()==1)
    check('Partial coverage remains visible',page.locator('#match-count').inner_text()=='56/624 prerequisites checked')
    shot(page,'overview')
    parent='section:university/MATH 101';child=parent+'>MATH 102'
    closed=toggle_frames(page,parent,child)
    check('Collapse animates retained nodes before removal',closed['immediate']['present'] and any(f['present'] and 0<f['opacity']<1 for f in closed['frames']) and not closed['frames'][-1]['present'])
    check('Collapse never changes camera or clicked anchor',all(f['camera']==closed['before'] and f['parent']==closed['anchor'] for f in closed['frames']))
    opened=toggle_frames(page,parent,child)
    check('Expansion grows and fades in rather than popping',opened['immediate']['animating']=='true' and any(0<f['opacity']<1 for f in opened['frames'] if f['present']) and len({f['pos'] for f in opened['frames']})>2 and opened['frames'][-1]['opacity']==1)
    check('Expansion preserves camera and clicked anchor on every sampled frame',all(f['camera']==opened['before'] and f['parent']==opened['anchor'] for f in opened['frames']))
    before=camera(page);page.locator('#zoom-in').click()
    page.mouse.move(1190,570);page.mouse.down();page.mouse.move(1110,530,steps=8);page.mouse.up();page.wait_for_timeout(100)
    check('User-controlled pan and zoom work',camera(page)!=before)
    changed=toggle_frames(page,parent,child)
    check('Expansion/collapse keeps a manually panned and zoomed camera intact',all(f['camera']==changed['before'] for f in changed['frames']))
    before=camera(page)
    page.evaluate('''async id=>{const n=document.querySelector('[data-node="'+id+'"]');for(let i=0;i<7;i++){n.dispatchEvent(new MouseEvent('click',{bubbles:true}));await new Promise(r=>setTimeout(r,45));}}''',parent)
    page.wait_for_timeout(450)
    check('Rapid toggles settle without recentering or duplicate nodes',camera(page)==before and page.locator('#viewport').get_attribute('data-animating')=='false' and page.locator('[data-node]').evaluate_all('xs=>new Set(xs.map(x=>x.dataset.node)).size===xs.length'))
    before=camera(page);page.locator('#jump-required').click();page.wait_for_timeout(400)
    check('Explicit major-required navigation moves camera',camera(page)!=before)
    before=camera(page);page.locator('[data-node="section:required/EE 202"]').dispatch_event('click');page.wait_for_timeout(400)
    check('Major course expands into prerequisite-dependent courses, no folders',page.locator('[data-node="section:required/EE 202>EE 303"]').count()==1 and camera(page)==before)
    shot(page,'major-required')
    page.locator('#jump-electives').click();page.wait_for_timeout(400)
    group=toggle_frames(page,'section:core','section:core/EE 302')
    check('Elective section lists expand smoothly without moving the camera',group['immediate']['animating']=='true' and any(f['present'] and 0<f['opacity']<1 for f in group['frames']) and all(f['camera']==group['before'] for f in group['frames']))
    before=camera(page);page.locator('[data-node="section:core"]').focus();page.keyboard.press('Enter');page.wait_for_timeout(400)
    check('Keyboard collapse preserves viewport',camera(page)==before and page.locator('[data-node="section:core"]').get_attribute('aria-expanded')=='false')
    page.locator('#reset-button').click();page.wait_for_timeout(400)
    check('Explicit reset restores the initial readable viewport',camera(page)=='translate(45 128) scale(1)')
    find(page,'EE202')
    check('Search opens a forward course map instead of a category list',page.locator('[data-node="focus:EE 202>EE 303"]').count()==1 and page.locator('#direction-label').inner_text()=='Prerequisite → course')
    page.locator('[data-node="focus:EE 202>EE 303"]').dispatch_event('click');page.wait_for_timeout(400)
    shot(page,'prerequisites')
    page.locator('[data-node="focus:EE 202"] [data-action="info"]').click()
    txt=page.locator('#course-content').inner_text()
    check('Course details preserve prerequisites, minimum grades and separate corequisites',all(s in txt for s in ['ENS 203','min D','EE 200','EE 202R','Opens next']))
    page.get_by_role('button',name='◇ Planned',exact=True).click()
    saved=json.loads(page.evaluate("localStorage.getItem('prereq.plan.v1:BSEE:202401')"))
    check('Plans remain local and cohort-specific',saved['marks']=={'EE 202':'planned'})
    page.get_by_role('button',name='✓ Completed',exact=True).click();page.locator('#close-course').click()
    page.locator('#list-tab').click();page.locator('#status-filter').select_option('completed')
    check('Completed list filter works',page.locator('.course-row').count()==1 and 'EE 202' in page.locator('.course-row').inner_text())
    page.locator('#plan-button').click()
    with page.expect_download() as event:page.get_by_role('button',name='Export JSON',exact=True).click()
    exported=json.loads(Path(event.value.path()).read_text())
    check('Export has only version, major, term and marks',set(exported)=={'schemaVersion','program','term','marks'})
    page.once('dialog',lambda d:d.accept())
    imported={**exported,'marks':{'CS 204':'planned'}}
    page.locator('#import-file').set_input_files({'name':'plan.json','mimeType':'application/json','buffer':json.dumps(imported).encode()})
    page.wait_for_timeout(100)
    check('Import replaces plan after confirmation','CS 204' in page.locator('#info-content').inner_text())
    page.locator('#import-file').set_input_files({'name':'wrong.json','mimeType':'application/json','buffer':json.dumps({**imported,'term':'202601'}).encode()})
    page.wait_for_timeout(100)
    check('Wrong-cohort import does not corrupt saved markers','exact major' in page.locator('#toast').inner_text() and 'CS 204' in page.locator('#info-content').inner_text())
    page.locator('#close-info').click();page.locator('#status-filter').select_option('all')
    detail(page,'EE401')
    check('Mixed AND/OR prerequisites shown without flattening logic','ALL OF' in page.locator('#course-content').inner_text() and 'ANY OF' in page.locator('#course-content').inner_text())
    page.get_by_role('button',name='Review prerequisite chain',exact=True).click();page.wait_for_timeout(450)
    check('Secondary upstream view preserves AND/OR groups',page.locator('.kind-logic').count()>=2 and page.locator('#direction-label').inner_text()=='Course → prerequisites')
    detail(page,'ECON201')
    check('Missing detail remains unknown, not no prerequisites','does not mean there are none' in page.locator('#course-content').inner_text())
    page.locator('#close-course').click();detail(page,'ENS491')
    check('Contextual program/cohort conditions are visible','80 completed SU credits' in page.locator('#course-content').inner_text())
    page.locator('#close-course').click();page.locator('#source-button').click()
    check('Sources show 57 bundled records, not fictitious complete coverage','57 bundled' in page.locator('#info-content').inner_text())
    page.locator('#close-info').click();page.locator('#change-major').click();page.locator('#major-select').select_option('BSCS');page.locator('#open-map').click()
    check('Unbundled major never receives substituted EE data','No offline snapshot' in page.locator('#empty-title').inner_text() and page.locator('[data-node]').count()==0)
    # Return to a snapshot after the empty state: keyed SVG maps must be rebuilt.
    page.locator('#change-major').click();page.locator('#major-select').select_option('BSEE');page.locator('#open-map').click();page.wait_for_timeout(450)
    check('Switching back rebuilds a working map',page.locator('[data-node="section:university"]').count()==1)
    check('Desktop JavaScript produced no errors',not errors)
    mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    choose(mobile)
    check('Mobile starts in the prerequisite map',mobile.locator('#graph-region').is_visible() and not mobile.locator('#list-region').is_visible())
    check('Mobile document does not overflow horizontally',mobile.evaluate('document.documentElement.scrollWidth<=window.innerWidth'))
    before=camera(mobile)
    mobile.locator('#graph').dispatch_event('pointerdown',{'pointerId':1,'pointerType':'touch','clientX':200,'clientY':500,'button':0})
    mobile.locator('#graph').dispatch_event('pointermove',{'pointerId':1,'pointerType':'touch','clientX':120,'clientY':450,'button':0})
    mobile.locator('#graph').dispatch_event('pointerup',{'pointerId':1,'pointerType':'touch','clientX':120,'clientY':450,'button':0})
    check('Touch pointer movement pans the map',camera(mobile)!=before)
    mobile.wait_for_timeout(100);mobile.locator('#reset-button').click();mobile.wait_for_timeout(400);shot(mobile,'mobile')
    detail(mobile,'EE202')
    check('Mobile course panel stays within viewport',mobile.locator('#course-panel').is_visible() and mobile.locator('#course-panel').bounding_box()['width']<=390)
    reduced=browser.new_page(viewport={'width':1280,'height':900},reduced_motion='reduce');choose(reduced)
    reduced.locator('[data-node="section:university/MATH 101"]').dispatch_event('click')
    check('Reduced motion respects system preference',reduced.locator('#viewport').get_attribute('data-animating')=='false' and reduced.locator('[data-node="section:university/MATH 101>MATH 102"]').count()==0)
    attack=browser.new_page(viewport={'width':1280,'height':900})
    payload='<img src=x onerror="window.__injected=true">'
    evil=html.replace('Electronic Circuits II',payload.replace('"','\\"'))
    attack.set_content(evil,wait_until='load');attack.locator('#open-map').click();attack.wait_for_timeout(450);detail(attack,'EE202')
    check('Source text is rendered literally, never injected as HTML',attack.locator('#course-content img').count()==0 and not attack.evaluate('Boolean(window.__injected)'))
    live=browser.new_page(viewport={'width':1440,'height':900})
    mock_script='''<script>window.fetch=async function(url){
      const seed=window.__MOCK_SEED__,ok=x=>new Response(JSON.stringify(x),{headers:{'Content-Type':'application/json'}}),path=String(url);
      if(path==='seed.json')return ok(seed);
      if(path.startsWith('api/degree'))return ok({data:seed.degrees['BSEE:202401'],meta:{state:'snapshot',observedAt:seed.observedAt,refreshing:false}});
      if(path.startsWith('api/index'))return new Promise(resolve=>{window.__pushIndex=()=>resolve(ok({data:{program:'BSEE',term:'202401',details:{'ECON 201':{code:'ECON 201',title:'Mock dependent course',prerequisite:{type:'course',code:'MATH 101',minGrade:'D'},corequisite:{type:'none'},observedAt:'2026-09-17',origin:'test'}}},meta:{refreshing:false}}));});
      throw new Error('Unexpected mock request '+path);
    };</script>'''
    live_html=html.replace('window.__PREVIEW_SEED__=','window.__MOCK_SEED__=').replace('<head>','<head>'+mock_script,1)
    live.set_content(live_html,wait_until='load');live.locator('#open-map').click();live.wait_for_timeout(450)
    live.locator('#zoom-in').click();before=camera(live)
    frames=live.evaluate('''async ()=>{const frames=[];window.__pushIndex();const start=performance.now();await new Promise(resolve=>{function frame(t){frames.push(document.getElementById('viewport').getAttribute('transform'));if(t-start<450)requestAnimationFrame(frame);else resolve();}requestAnimationFrame(frame);});return frames;}''')
    check('Background index results add edges without moving the viewport',all(f==before for f in frames) and live.locator('[data-node="section:university/MATH 101>ECON 201"]').count()==1)
    browser.close()
print(f'\n{len(checks)} browser checks passed. Actual Chromium rendering; simulated localStorage; no live upstream validation.')
if args.screenshots:
    (args.screenshots/'browser-checks.json').write_text(json.dumps(dict(passed=len(checks),checks=checks),indent=2)+'\n')
