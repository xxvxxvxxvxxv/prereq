"""Build the explicitly dated EE fixture from fact-only, manually transcribed rows."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prereq.catalog import code, course_url, degree_url, PROGRAM_MAP, LABELS, parse_expression
from urllib.parse import urlencode

stamp = '2026-09-17'
source = degree_url('BSEE','202401')
sections=[]
counts = {'university':24,'required':15,'core':39,'area':140,'free':406}
rules = {
 'university':'Complete 16 courses / 41 SU credits: the listed 1XX courses, PROJ 201, SPS 303, and ONE of the listed HUM courses. The eight other HUM options are alternatives, not extra obligations.',
 'required':'Complete the required courses, choosing MATH 212 OR the pair MATH 201 + MATH 202. Surplus courses from this mathematics alternative do not count toward elective pools. The official summary specifies 33 SU credits and 13 courses.',
 'core':'At least 25 SU credits from the core pool, including at least 9 SU credits of 400-level EE courses. Extra courses in this pool can count toward Area requirements.',
 'area':'At least 9 SU credits. Include at least one course from CS 300, CS 401, CS 412, ME 303, PHYS 302, PHYS 303, or an EE 48XXX special-topics course. Extra courses in this pool can count toward Free requirements.',
 'free':'At least 15 SU credits from FASS, SBS and FENS courses, excluding University Courses. School of Languages courses do not count in the free-elective pool.'}
flags = set('EE200 EE202 ENS203 ENS211 MATH201 MATH202 MATH203 MATH204 MATH212 CS201 CS204 ENS201 ENS206 DSA201 DSA210 ENS202 ENS204 ENS205 ENS207 ENS208 ENS209 ENS210 ENS216 MAT204 NS213 NS214 NS218 PHYS113'.split())
for key in counts:
    pool = source
    if key in {'core','area','free'}:
        pool = 'https://suis.sabanciuniv.edu/prod/SU_DEGREE.p_list_courses?' + urlencode(dict(P_AREA='BSEE_'+{'core':'CEL','area':'ARE','free':'FRE'}[key],P_LANG='EN',P_LEVEL='UG',P_PROGRAM='BSEE',P_TERM='202401'))
    courses=[]
    for line in (ROOT/'data'/f'{key}.tsv').read_text(encoding='utf-8').splitlines():
        p = line.split('|'); cid=code(p[0]); subject=cid.split()[0]
        faculty='FENS'
        if key=='free':
            faculty = 'SBS' if subject in {'ACC','ENT','FIN','MGMT','MKTG','OPIM','ORG'} or cid=='IF 201' else 'FENS' if subject in {'BIO','CHEM','CS','ENS','IE','IF','MATH','MAT','ME','NS','PHYS','XM'} else 'FASS'
        courses.append(dict(code=cid,title=p[1],ects=int(p[2]) if len(p)>2 else 6,credits=int(p[3]) if len(p)>3 else 3,faculty=p[4] if len(p)>4 else faculty,facultyCourse=True if p[0] in flags else None,source=course_url(cid),poolSource=pool))
    assert len(courses)==counts[key]
    sections.append(dict(id=key,label=LABELS[key],rule=rules[key],courses=courses,source=pool))
summary=[]
for label,ects,credits,n in [('University Courses',None,41,None),('Required Courses',None,33,13),('Core Electives',None,25,None),('Area Electives',None,9,None),('Free Electives',None,15,None),('Engineering',90,None,None),('Faculty Courses',None,None,5),('Basic Science',60,None,None)]:
    summary.append(dict(label=label,ects=ects,credits=credits,courses=n))
notes=[dict(label=LABELS[k],text=v) for k,v in rules.items()]+[
 dict(label='Faculty Courses',text='At least five faculty courses. At least two must be MATH-coded and at least three must be FENS Faculty Courses. These conditions overlap other degree requirements; do not add them as separate credits.'),
 dict(label='Engineering and Basic Science',text='At least 90 Engineering ECTS and 60 Basic Science ECTS. Their contributions overlap other requirements. Consult the credit distributions in the course catalog.'),
 dict(label='Pool priority and graduate courses',text='A course in more than one pool is listed under the earliest applicable category in the official summary. Graduate courses may qualify but are not listed in undergraduate pools. Check individual exceptions in official Degree Evaluation.'),
 dict(label='Planning, not a degree audit',text='These rules are a paraphrase of the official source. Completed marks do not verify grades, GPA, equivalence, substitutions, waivers, double-counting or registration eligibility. The university’s Degree Evaluation is authoritative.')]
degree=dict(schemaVersion=1,program=PROGRAM_MAP['BSEE'],term='202401',termLabel='Fall 2024–2025',source=source,summary=summary,total=dict(label='Total',ects=240,credits=125,courses=None),sections=sections,notes=notes,
    observedAt=stamp,origin='bundled',warnings=['Bundled, manually transcribed snapshot. Refresh against the official source before registration.'],
    choices=[dict(id='hum',type='one-of',codes=[c['code'] for c in sections[0]['courses'] if c['code'].startswith('HUM ')]),dict(id='math',type='either',options=[['MATH 212'],['MATH 201','MATH 202']])])
# Requirement facts read from each course's official public detail page.
# Only these courses have bundled prerequisite details. Others are explicitly unknown offline.
raw=[
 ('EE 202','ENS 203 - Undergraduate - Min Grade D','EE 200 and EE 202R'),
 ('ENS 203','MATH 102 - Undergraduate - Min Grade D','ENS 203R'),
 ('MATH 102','MATH 101 - Undergraduate - Min Grade D','MATH 102R'),
 ('MATH 101','__','MATH 101R'),
 ('EE 303','EL 202 - Undergraduate - Min Grade D or EE 202 - Undergraduate - Min Grade D','EE 303R'),
 ('CS 204','CS 201 - Undergraduate - Min Grade D','CS 204L'),
 ('CS 201','IF 100 - Undergraduate - Min Grade D','CS 201R'),
 ('ENS 211','MATH 101 - Undergraduate - Min Grade D','ENS 211R'),
 ('EE 313','ENS 211 - Undergraduate - Min Grade D','EE 313R')]
bycode={c['code']:c for s in sections for c in s['courses']}
details={}
for cid,pr,co in raw:
    c=bycode[cid]
    details[cid]={k:c[k] for k in ('code','title','credits','ects','source')}
    details[cid].update(prerequisite=parse_expression(pr),corequisite=parse_expression(co),prerequisiteText=pr,corequisiteText=co,generalRequirements='',scope='Current course catalog observed on 17 Sep 2026; not historical requirements.',observedAt=stamp,origin='bundled')
# Reviewed v2 supplement. None / unknown must not be converted into a no-prerequisite assertion.
facts=json.loads((ROOT/'data'/'prerequisite-facts.json').read_text(encoding='utf-8'))
for record in facts['records']:
    cid=record['code']; c=bycode[cid]
    d={k:c[k] for k in ('code','title','credits','ects','source')}
    d.update(prerequisite=parse_expression(record['prerequisite']),
        corequisite=parse_expression(record.get('corequisite')) if record.get('corequisite') is not None else dict(type='unknown',reason='Blank corequisite field; verify the source.'),
        prerequisiteText=record['prerequisite'],corequisiteText=record.get('corequisite') or '',
        generalRequirements=record.get('generalRequirements',''),scope='Current catalog; degree admission-term rules remain separate.',
        observedAt=facts['observedAt'],origin='bundled')
    if record.get('unknownReason'):
        d['prerequisite']=dict(type='unknown',reason=record['unknownReason'])
    details[cid]=d
seed=dict(schemaVersion=1,programs=list(PROGRAM_MAP.values()),degrees={'BSEE:202401':degree},details=details,observedAt=stamp)
bio_path=ROOT/'data'/'bio-202401-degree.json'
if bio_path.exists():
    seed['degrees']['BSBIO:202401']=json.loads(bio_path.read_text(encoding='utf-8'))
seed['catalogTerms']=[{'id':'202601','label':'Fall 2026–2027','source':'User-supplied Banner selector and POST screenshots'}]
seed['catalogDetails']={}
seed['legacyDetailScope']='Unversioned source examples; never prerequisites for a selected catalog term.'
for detail in seed['details'].values():
    detail.update(catalogTerm=None,sourceRole='unversioned-reference')
(ROOT/'web'/'seed.json').write_text(json.dumps(seed,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print('Seed:',sum(len(s['courses']) for s in sections),'courses,',len(details),'detail records')
