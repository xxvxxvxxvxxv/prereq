#!/usr/bin/env python3
from pathlib import Path
import subprocess
import re
import html as htmlmod

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"
APP = ROOT / "web" / "app.js"
CSS = ROOT / "web" / "styles.css"

def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"Could not find expected {label}. No partial patch was written.")
    return text.replace(old, new, 1)

def project_url():
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT,
            text=True,
        ).strip()
    except Exception:
        return "#"

    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote.split("git@github.com:", 1)[1]
    if remote.endswith(".git"):
        remote = remote[:-4]
    return remote

repo_url = project_url()

# ---------- index.html ----------
index = INDEX.read_text(encoding="utf-8")

index = replace_once(
    index,
    '<button id="rules-button" class="quiet">Rules</button>',
    '<button id="rules-button" class="quiet">Degree links</button>',
    "Rules button",
)

old_footer = '<footer class="app-footer"><span id="footer-status">Public catalog · no university login</span><span class="footer-right">Independent tool <span>·</span> made by xxv <button id="help-button" aria-label="Help and keyboard shortcuts">?</button></span></footer>'
new_footer = (
    '<footer class="app-footer">'
    '<span id="footer-status" hidden></span>'
    f'<a class="project-link" href="{htmlmod.escape(repo_url, quote=True)}" '
    'target="_blank" rel="noopener noreferrer">made by xxv</a>'
    '</footer>'
)
index = replace_once(index, old_footer, new_footer, "footer")
INDEX.write_text(index, encoding="utf-8")

# ---------- app.js ----------
app = APP.read_text(encoding="utf-8")

old_external = "function externalLink(label,url){const a=el('a','source-link',label);try{const u=new URL(url);if(u.protocol==='https:'&&u.hostname==='suis.sabanciuniv.edu'){a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}else a.removeAttribute('href');}catch{}return a;}"
new_external = "function externalLink(label,url){const a=el('a','source-link',label);try{const u=new URL(url);const host=u.hostname.toLowerCase();if(u.protocol==='https:'&&(host==='sabanciuniv.edu'||host.endsWith('.sabanciuniv.edu'))){a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}else a.removeAttribute('href');}catch{}return a;}"
app = replace_once(app, old_external, new_external, "official externalLink allow-list")

old_rules = "function rules(){if(!state.degree)return toast('Open a course map first.');const box=openInfo('DEGREE RULES');box.append(heading(state.degree.program.name),text(state.degree.termLabel+' · first admission term'));const total=el('div','totals-grid');for(const[n,l]of [[state.degree.total.credits,'SU credits minimum'],[state.degree.total.ects,'ECTS minimum']]){const d=el('div');d.append(el('strong','',String(n)),el('span','',l));total.append(d);}box.append(total);box.append(text('Course options are not all mandatory. Elective pools, choice rules and overlapping credit requirements must be read together.','audit-warning'));const table=el('table','summary-table');const head=el('tr');for(const v of ['CATEGORY','MIN. SU','MIN. ECTS','COURSES'])head.append(el('th','',v));table.append(head);for(const r of state.degree.summary){const tr=el('tr');for(const v of [r.label,r.credits??'·',r.ects??'·',r.courses??'·'])tr.append(el('td','',String(v)));table.append(tr);}box.append(table);for(const r of state.degree.notes){const card=el('section','rule-card');card.append(el('h3','',r.label),text(r.text));box.append(card);}box.append(externalLink('Read the official degree requirements ↗',state.degree.source));}"
new_rules = """function rules(){
    if(!state.degree)return toast('Open a course map first.');
    const box=openInfo('DEGREE REQUIREMENTS');
    box.append(
      heading('Official degree requirements'),
      text(admissionLabel(state.degree.term)+' · opens Sabancı in a new tab','muted-small')
    );
    const list=el('div','degree-link-list');
    const current=state.degree.program.id;
    const programs=[...state.seed.programs].sort((a,b)=>{
      if(a.id===current)return -1;
      if(b.id===current)return 1;
      return a.name.localeCompare(b.name);
    });
    for(const program of programs){
      const degree=state.seed.degrees[`${program.id}:${state.degree.term}`];
      if(!degree?.source)continue;
      const link=externalLink(program.name+' ↗',degree.source);
      if(program.id===current)link.classList.add('current');
      list.append(link);
    }
    box.append(list);
  }"""
app = replace_once(app, old_rules, new_rules, "degree rules dialog")

old_events = "$('jump-university').onclick=()=>jumpSection('university');$('jump-required').onclick=()=>jumpSection('required');$('jump-electives').onclick=()=>jumpSection('core');$('match-count').onclick=coverageInfo;$('rules-button').onclick=rules;$('plan-button').onclick=myPlan;$('source-button').onclick=sources;$('help-button').onclick=help;$('refresh-button').onclick=refresh;"
new_events = "$('jump-university').onclick=()=>jumpSection('university');$('jump-required').onclick=()=>jumpSection('required');$('jump-electives').onclick=()=>jumpSection('core');$('match-count').onclick=coverageInfo;$('rules-button').onclick=rules;$('plan-button').onclick=myPlan;$('source-button').onclick=sources;$('refresh-button').onclick=refresh;"
app = replace_once(app, old_events, new_events, "help-button event binding")

APP.write_text(app, encoding="utf-8")

# ---------- styles.css ----------
css = CSS.read_text(encoding="utf-8")

old_footer_css = ".app-footer{height:35px;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 27px;font-size:9px;border-top:1px solid #222;background:#000;color:#fff}.app-footer #footer-status{opacity:.65;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.footer-right{display:flex;gap:8px;align-items:center;white-space:nowrap;opacity:.65}.footer-right button{border:1px solid #666;border-radius:50%;width:15px;height:15px;padding:0;font-size:10px}"
new_footer_css = ".app-footer{height:35px;display:flex;align-items:center;justify-content:flex-end;padding:0 27px;font-size:9px;border-top:1px solid #222;background:#000;color:#fff}.project-link{color:#fff;text-decoration:none;opacity:.68}.project-link:hover{opacity:1;text-decoration:underline;text-underline-offset:3px}"
css = replace_once(css, old_footer_css, new_footer_css, "footer styles")

anchor = ".source-link{display:inline-block;margin-top:17px;font-size:10px;color:#fff;text-decoration:underline;text-underline-offset:3px}"
extra = anchor + ".degree-link-list{display:flex;flex-direction:column;gap:8px;margin-top:18px}.degree-link-list .source-link{display:block;margin:0;padding:10px 11px;border:1px solid #303030;border-radius:5px;text-decoration:none}.degree-link-list .source-link:hover{background:#141414;border-color:#555}.degree-link-list .source-link.current{border-color:#777;background:#0d0d0d}"
css = replace_once(css, anchor, extra, "degree link list styles")

# Keep mobile footer simple.
css = css.replace(
    ".footer-right{font-size:7px;gap:5px}.footer-right>span{display:none}",
    ".project-link{font-size:8px}",
)

CSS.write_text(css, encoding="utf-8")

print("Final link/footer cleanup applied.")
print("- official Sabanci links are clickable on sabanciuniv.edu + subdomains")
print("- Rules renamed to Degree links")
print("- Degree links panel lists every bundled major for the selected admission term")
print("- footer now contains only clickable 'made by xxv'")
print("- help '?' removed")
print("Project link:", repo_url)
