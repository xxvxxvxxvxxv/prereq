"""Extract a degree-page snapshot without inventing offerings or prerequisite rules."""
from __future__ import annotations
import hashlib
from .catalog import CatalogError, catalog_link, parse_degree


def extract_degree_snapshot(html: str, source: str) -> dict:
    """Parse one saved degree page; linked pools stay explicitly incomplete.

    This is deliberately not a complete live-degree response. It must not be
    stored as a verified full map until every required linked pool is checked.
    A degree's admissionTerm is not a semester-offering/catalog term.
    """
    operation, params = catalog_link(source)
    if operation != 'su_degree.p_degree_detail':
        raise CatalogError('Supply the original official degree-detail URL.')
    program = params.get('P_PROGRAM', [''])[0]
    admission_term = params.get('P_TERM', [''])[0]
    result = parse_degree(html, program, admission_term, source)
    pending = result['poolLinks']
    for section in result['sections']:
        parts = section.get('subsections') or [section]
        for part in parts:
            incomplete = part['id'] in pending
            part['dataStatus'] = 'linked-pool-not-loaded' if incomplete else 'embedded-in-saved-page'
            part['complete'] = not incomplete
            # Null means unknown, not a verified pool of zero options.
            part['totalCourseOptions'] = None if incomplete else len(part['courses'])
        section['complete'] = all(p['complete'] for p in parts)
        section['totalCourseOptions'] = len(section['courses']) if section['complete'] else None
    result.update(
        sourceRole='degree-requirements',
        admissionTerm=admission_term,
        catalogTerm=None,
        origin='user-supplied-html',
        observedAt=None,
        contentSha256=hashlib.sha256(html.encode('utf-8')).hexdigest(),
        degreePoolsComplete=not bool(pending),
        availability={'status': 'not-provided', 'source': None, 'catalogTerm': None},
        prerequisiteData={'status': 'not-provided', 'source': None},
    )
    result['warnings'].append(
        'This page supplies cohort-specific degree requirements only. '
        'Linked elective pools, semester offerings and course prerequisites '
        'have not been fetched by this extraction.'
    )
    return result
