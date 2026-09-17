#!/usr/bin/env python3
"""Read-only PREREQ source check using the same adapters as the application.
No GitHub API, deployments, credentials, cookies from a user, or account changes.
The temporary test cache is deleted on exit. Only a small JSON report is written.
"""
from __future__ import annotations
import argparse,json,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from prereq import __version__
from prereq.catalog import PROGRAM_MAP,TERM_RE,code
from prereq.network import OfficialClient
from prereq.service import CatalogService

def main():
    p=argparse.ArgumentParser(description='Read the official PREREQ sources without deploying or editing any account.')
    p.add_argument('--program',default='BSBIO',choices=PROGRAM_MAP)
    p.add_argument('--term','--admission-term',dest='admission',default='202401')
    p.add_argument('--catalog-term',default='202601')
    p.add_argument('--schedule-term',default='202601')
    p.add_argument('--course',default='BIO 303')
    p.add_argument('--report',type=Path,default=ROOT/'source-check.json')
    args=p.parse_args()
    if not all(TERM_RE.fullmatch(x) for x in (args.admission,args.catalog_term,args.schedule_term)):
        p.error('Terms must use the six-digit official identifier, for example 202601.')
    try:cid=code(args.course)
    except ValueError:p.error('Invalid course code.')
    records=[]
    with tempfile.TemporaryDirectory(prefix='prereq-source-check-') as temp:
        service=CatalogService(ROOT,Path(temp)/'catalog.sqlite3',client=OfficialClient())
        stages=[('prerequisite',f'course:{args.catalog_term}:{cid}'),
                ('degree',f'degree:{args.program}:{args.admission}'),
                ('catalog',f'catalog:{args.catalog_term}'),
                ('schedule',f'schedule:{args.schedule_term}:{cid}')]
        try:
            for stage,key in stages:
                start=time.monotonic()
                record={'stage':stage,'key':key,'checkedAt':datetime.now(timezone.utc).isoformat(timespec='seconds')}
                try:
                    data=service.load(key);service.store.put(key,data)
                    record.update(ok=data.get('complete',True),source=data.get('source'),provenance=data.get('provenance',[]))
                    if stage=='catalog':record['courses']=len(data['courses'])
                    elif stage=='degree':record.update(program=data['program']['id'],admissionTerm=data['term'],pools=[{'id':s['id'],'complete':s.get('complete',True),'count':s.get('totalCourseOptions')} for s in data['sections']],poolErrors=data.get('poolErrors',[]))
                    elif stage=='prerequisite':
                        record.update(code=data['code'],catalogTerm=data['catalogTerm'],prerequisite=data['prerequisite'],corequisite=data['corequisite'])
                        if data['prerequisite']['type']=='unknown':record.update(ok=False,message='Source received, but prerequisite expression needs review.')
                    else:record.update(code=data['code'],scheduleTerm=data['scheduleTerm'],offered=data['offered'],sections=len(data['sections']))
                except Exception as exc:
                    record.update(ok=False,errorType=type(exc).__name__,message=str(exc)[:800])
                record['seconds']=round(time.monotonic()-start,3);records.append(record)
                print(json.dumps(record,ensure_ascii=False),flush=True)
                if not record['ok'] and any(x in record.get('message','') for x in ('DNS lookup failed','HTTP 401','HTTP 403','HTTP 429','HTTP 503','verification page','cooldown')):
                    # Avoid repeated requests when the network or source asks us to stop.
                    for next_stage,next_key in stages[len(records):]:
                        records.append({'stage':next_stage,'key':next_key,'ok':False,'skipped':True,'reason':'Stopped after upstream/network refusal; no repeated attempts.'})
                    break
        finally:service.close()
    report={'version':__version__,'allVerified':all(x['ok'] for x in records),'checks':records,
            'scope':'Direct, anonymous read-only source checks from this runtime. No account or deployment operations.'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if report['allVerified'] else 1
if __name__=='__main__':raise SystemExit(main())
