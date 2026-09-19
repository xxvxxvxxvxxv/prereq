#!/usr/bin/env python3
"""Explicit, bounded live verification from a network that can reach public SUIS.
Does not bypass robots, authentication or upstream access controls.
"""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from prereq.service import CatalogService
from prereq.catalog import PROGRAM_MAP, CatalogError
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--program',choices=PROGRAM_MAP,default='BSEE')
p.add_argument('--term',default='202401')
p.add_argument('--course',default='EE 202',help='Also verify one current course page')
args=p.parse_args()
service=CatalogService(ROOT,ROOT/'.cache'/'catalog.sqlite3')
try:
    key=f'degree:{args.program}:{args.term}'
    degree=service.load(key)
    service.store.put(key,degree)
    detail=service.load('course:'+args.course)
    service.store.put('course:'+args.course,detail)
    print(json.dumps(dict(program=degree['program']['name'],term=degree['termLabel'],
        observedAt=degree['observedAt'],pools={s['label']:len(s['courses']) for s in degree['sections']},
        course=detail['code'],prerequisite=detail['prerequisite'],corequisite=detail['corequisite']),indent=2,ensure_ascii=False))
    print('\nLive verification succeeded for THIS major, admission term and course only.')
except (CatalogError,OSError) as exc:
    print(f'Live verification did not succeed: {exc}',file=sys.stderr)
    print('Open the official source manually. No fabricated data or access bypass is used.',file=sys.stderr)
    sys.exit(1)
finally:
    service.close()
