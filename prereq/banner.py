"""Term-specific Banner catalog and schedule adapters.

The catalog request shape is transcribed from the supplied browser Form Data.
HTML adapters fail closed on a wrong term, incomplete response, or unknown
prerequisite syntax. Department pages never create term-specific edges here.
"""
from __future__ import annotations
from html import unescape
from bisect import bisect_left
import re
from urllib.parse import urljoin, urlsplit, parse_qs
from .catalog import CatalogError, Document, Node, clean, code, numeric, term_label, TERM_RE, parse_expression

HOST = 'https://suis.sabanciuniv.edu'
CATALOG_START = HOST + '/prod/bwckctlg.p_disp_dyn_ctlg'
CATALOG_SEARCH = HOST + '/prod/bwckctlg.p_display_courses'
SCHEDULE_START = HOST + '/prod/bwckschd.p_disp_dyn_sched'
CAPTURED_SUBJECTS = ('AL ACCA ACC GR AR MART ANTH ARA BP BAN CHEM CIP CS CONF CULT DA DSA DS DT '
    'ECNA ECON EE ETM ENRG ENS ENG ENT ES FIN MFIN FRE GEN GER HART HIST HUM IE IT IF IR IS LAW LIT '
    'MJC MGMT MRES MFE MFG MIM MKTG MAT MATH ME BIO NS OPIM ORG PERS PHIL PHYS PSIR POLS PROJ XM '
    'PSY QL SEC SPS SOC SPA TLL TS TUR VA').split()


def catalog_form(term: str, subjects: list[str]) -> list[tuple[str, str]]:
    if not TERM_RE.fullmatch(term) or not subjects or len(subjects) > 300:
        raise CatalogError('Select a valid catalog term and subjects.')
    if len(set(subjects)) != len(subjects) or any(not re.fullmatch(r'[A-Z]{2,8}', s) for s in subjects):
        raise CatalogError('Invalid or repeated subject code.')
    fields = [('term_in', term), ('call_proc_in', 'bwckctlg.p_disp_dyn_ctlg')]
    fields += [(k, 'dummy') for k in ('sel_subj','sel_levl','sel_schd','sel_coll','sel_divs','sel_dept','sel_attr')]
    fields += [('sel_subj', s) for s in subjects]
    fields += [(k, '') for k in ('sel_crse_strt','sel_crse_end','sel_title')]
    fields += [(k, '%') for k in ('sel_levl','sel_schd','sel_coll','sel_divs','sel_dept')]
    fields += [('sel_from_cred', ''), ('sel_to_cred', ''), ('sel_attr', '%')]
    return fields


def forms(html: str, source: str):
    d = Document(html)
    return [(n, urljoin(source, unescape(n.attrs.get('action', '')))) for n in d.nodes if n.tag == 'form']


def pick_form(html: str, source: str, operation: str):
    for form, url in forms(html, source):
        if urlsplit(url).hostname == 'suis.sabanciuniv.edu' and urlsplit(url).path == '/prod/' + operation:
            return form, url
    raise CatalogError('Expected public Banner form was not found: ' + operation)


def term_options(html: str):
    d = Document(html)
    values = {}
    for n in d.nodes:
        if n.tag == 'select' and n.attrs.get('name', '').lower() in {'term_in', 'cat_term_in', 'p_term', 'p_term_in'}:
            for op in n.all('option'):
                val = op.attrs.get('value', '')
                if TERM_RE.fullmatch(val):
                    # The numeric identifier is the key; the actual source label
                    # is retained (it may include 'View Only' or archive text).
                    values[val] = dict(id=val, label=op.text() or term_label(val))
    if not values:
        raise CatalogError('No catalog terms were returned by the official selector.')
    return [values[k] for k in sorted(values, reverse=True)]


def term_fields(form: Node, term: str):
    names = {n.attrs.get('name') for n in form.all('select')
             if n.attrs.get('name', '').lower() in {'term_in', 'cat_term_in', 'p_term', 'p_term_in'}}
    if not names:
        raise CatalogError('No term control found in the official selector form.')
    return form_fields(form, {name:term for name in names})


def form_fields(form: Node, overrides: dict):
    result = []
    for n in form.all():
        name = n.attrs.get('name')
        if not name or 'disabled' in n.attrs:
            continue
        if n.tag == 'input':
            typ = n.attrs.get('type', 'text').lower()
            if typ in {'password', 'file'}:
                raise CatalogError('Refusing an authenticated or upload form.')
            if typ in {'submit', 'button', 'image', 'reset'}:
                continue
            if typ in {'checkbox', 'radio'} and 'checked' not in n.attrs:
                continue
            # Hidden 'dummy' entries are intentional Banner array parameters.
            value = n.attrs.get('value', '') if typ == 'hidden' and n.attrs.get('value') == 'dummy' else overrides.get(name, n.attrs.get('value', ''))
            result.append((name, str(value)))
        elif n.tag == 'select':
            options = [(o.attrs.get('value', o.text()), o) for o in n.all('option')]
            if name in overrides:
                value = str(overrides[name])
                if value not in {v for v, _ in options}:
                    raise CatalogError('The selected value is not listed by the official form: ' + name)
                result.append((name, value))
            else:
                selected = [v for v, o in options if 'selected' in o.attrs]
                if not selected:
                    vals = [v for v, _ in options]
                    selected = ['%'] if '%' in vals else [''] if '' in vals else vals[:1]
                if 'multiple' not in n.attrs:
                    selected = selected[:1]
                result.extend((name, v) for v in selected)
    return result


def _term_check(d: Document, term: str):
    if not TERM_RE.fullmatch(term):
        raise CatalogError('Invalid catalog term.')
    # Look in the page header, not a course's description or old-offering list.
    headers = [n for n in d.nodes if 'ddtitle' in n.attrs.get('class', '').split()]
    limit = headers[0].start if headers else 10**9
    header = clean(' '.join(t for p, t in d.tokens if p < limit))
    season = ['Fall','Spring','Summer'][int(term[-1])-1]
    year = int(term[:4])
    pattern = rf'\b{season}\s+{year}\s*[-–/]\s*{year+1}\b'
    if not re.search(pattern, header, re.I):
        raise CatalogError('The source does not confirm the selected catalog/schedule term.')


def _segment(d, start, stop):
    if not hasattr(d, '_token_positions'):
        d._token_positions = [p for p, _ in d.tokens]
    a, b = bisect_left(d._token_positions, start), bisect_left(d._token_positions, stop)
    return clean(' '.join(t for _, t in d.tokens[a:b]))


def _detail_identity(url):
    u = urlsplit(url)
    if u.hostname != 'suis.sabanciuniv.edu' or u.path != '/prod/bwckctlg.p_disp_course_detail':
        return None
    q = parse_qs(u.query, keep_blank_values=True)
    if any(len(v) != 1 for v in q.values()):
        raise CatalogError('Ambiguous course-detail link.')
    try:
        return code(q['subj_code_in'][0] + ' ' + q['crse_numb_in'][0]), q['cat_term_in'][0]
    except (KeyError, ValueError):
        return None


def _field(text, name):
    boundaries = r'(?:Prerequisites?|Corequisites?|General Requirements|Restrictions|Registration Restrictions|Levels|Schedule Types|Faculty|Course Attributes|Equivalent Courses|Mutually Exclusive|Repeat Status|Credit hours|Release)\s*:'
    m = re.search(r'\b' + name + r'\s*:\s*(.*?)(?=\b' + boundaries + r'|$)', text, re.I)
    return clean(m[1]) if m else None


def _strip_footer(value):
    if value is None:
        return None
    return re.split(r'\b(?:Return to Previous|Return to Menu|Skip to top of page|Release\s*:\s*\d|Select the desired Schedule Type)\b', value, maxsplit=1, flags=re.I)[0].strip()


def banner_expression(raw: str | None):
    if raw is None:
        return dict(type='unknown', raw='', reason='No explicit prerequisite field in this response.')
    value = _strip_footer(clean(raw))
    if value.lower() in {'none', 'no prerequisites', 'no prerequisite', 'not required', '__', '_', '-', 'n/a'}:
        return dict(type='none', raw=raw)
    concurrent = {}
    # Convert only complete, recognized Banner course clauses. Unrecognized
    # credits, score tests, standing, or approval conditions remain unknown.
    clause = re.compile(
        r'(?:Undergraduate\s+level\s+|Course\s+or\s+Test\s*:\s*)?'
        r'([A-Z]{2,8}\s+\d{3,5}[A-Z]{0,2})'
        r'(?:\s+Minimum\s+Grade(?:\s+of)?\s+([A-Z][+-]?))'
        r'(?:\s+(May\s+(?:not\s+)?be\s+taken\s+concurrently)\.?)?', re.I)
    def replace(m):
        cid = code(m[1])
        if m[3]:
            concurrent[cid] = 'not' not in m[3].lower()
        return cid + ' - Undergraduate - Min Grade ' + m[2].upper()
    value = clause.sub(replace, value)
    value = re.sub(r'\bUndergraduate\s+level\s+(?=[A-Z]{2,8}\s*\d)', '', value, flags=re.I)
    # Do not discard non-course rules or logical operators.
    parsed = parse_expression(value)
    if parsed['type'] == 'unknown':
        parsed['raw'] = raw
        parsed['reason'] = 'The catalog includes a condition requiring review; no eligibility is inferred.'
        return parsed
    def annotate(node):
        if node['type'] == 'course' and node['code'] in concurrent:
            node['concurrentAllowed'] = concurrent[node['code']]
        for child in node.get('children', []):
            annotate(child)
    annotate(parsed)
    parsed['raw'] = raw
    return parsed


def parse_entries(html: str, term: str, source=CATALOG_SEARCH):
    d = Document(html)
    if 'Catalog Entries' not in d.text:
        raise CatalogError('The catalog response is not a course-results page.')
    _term_check(d, term)
    anchors = []
    for n in d.nodes:
        if n.tag != 'a':
            continue
        target = urljoin(source, unescape(n.attrs.get('href', '')))
        ident = _detail_identity(target)
        if not ident:
            continue
        cid, linked_term = ident
        if linked_term != term:
            raise CatalogError('A course link belongs to a different catalog term.')
        parent = n.ancestor('th') or n.ancestor('td') or n
        # Nested/table duplicate links for the same record do not create copies.
        if anchors and anchors[-1][1] == cid and anchors[-1][0].start == parent.start:
            continue
        anchors.append((parent, cid, target, n.text()))
    if not anchors:
        raise CatalogError('No course-detail links were found; the catalog snapshot was not replaced.')
    records = {}
    details = {}
    node_positions = [n.start for n in d.nodes]
    for i, (node, cid, target, label) in enumerate(anchors):
        stop = anchors[i+1][0].start if i+1 < len(anchors) else d.pos + 1
        block = _segment(d, node.start, stop)
        title = re.sub(r'^' + re.escape(cid) + r'\s*[-–:]?\s*', '', label, flags=re.I)
        title = re.sub(r'\s*\[\s*Syllabus\s*\]\s*$', '', title, flags=re.I).strip()
        credits = re.search(r'(\d+(?:\.\d+)?)\s+Credit\s+hours?', block, re.I)
        ects = re.search(r'\b(\d+(?:\.\d+)?)\s+ECTS\b', block, re.I)
        links = []
        for a in d.nodes[bisect_left(node_positions, node.start):bisect_left(node_positions, stop)]:
            if a.tag == 'a':
                link = urljoin(source, unescape(a.attrs.get('href', '')))
                u = urlsplit(link)
                if u.hostname == 'suis.sabanciuniv.edu' and u.path.startswith('/prod/bwckschd.'):
                    q = parse_qs(u.query)
                    if q.get('term_in') == [term]:
                        links.append(link)
        item = dict(code=cid, title=title or cid, credits=numeric(credits[1]) if credits else None,
                    ects=numeric(ects[1]) if ects else None, source=target, catalogTerm=term,
                    scheduleLinks=list(dict.fromkeys(links)), sourceRole='course-catalog')
        if cid in records and records[cid] != item:
            raise CatalogError('Conflicting duplicate catalog entries: ' + cid)
        records[cid] = item
        prereq, coreq = _field(block, 'Prerequisites?'), _field(block, 'Corequisites?')
        if prereq is not None:
            details[cid] = dict(item, prerequisite=banner_expression(prereq), corequisite=banner_expression(coreq),
                prerequisiteText=prereq, corequisiteText=coreq or '',
                generalRequirements=_strip_footer(_field(block, '(?:General Requirements|Restrictions)')) or '',
                scope='Official Banner course catalog for ' + term_label(term))
    if len(records) > 6000:
        raise CatalogError('Unexpectedly large catalog.')
    return dict(schemaVersion=1, catalogTerm=term, termLabel=term_label(term),
                courses=records, details=details, complete=True, source=source,
                sourceRole='course-catalog', availability='not-inferred-from-catalog')


def parse_detail(html: str, cid: str, term: str, source: str):
    cid = code(cid)
    if _detail_identity(source) != (cid, term):
        raise CatalogError('Course detail URL does not match the requested course and term.')
    d = Document(html)
    _term_check(d, term)
    heads = [n for n in d.nodes if 'ddtitle' in n.attrs.get('class', '').split()]
    heading = next((n.text() for n in heads if re.search(r'\b'+re.escape(cid)+r'\b', n.text())), None)
    if not heading:
        # Some Banner templates use h2 rather than ddtitle.
        heading = next((n.text() for n in d.nodes if n.tag in {'h1','h2','h3'} and re.match(re.escape(cid)+r'\b', n.text())), None)
    if not heading:
        raise CatalogError('Requested course heading was not present in the detail response.')
    title = re.sub(r'^.*?' + re.escape(cid) + r'\s*[-–:]?\s*', '', heading).strip()
    text = d.text
    prereq = _strip_footer(_field(text, 'Prerequisites?'))
    coreq = _strip_footer(_field(text, 'Corequisites?'))
    general = _strip_footer(_field(text, 'General Requirements')) or ''
    restrictions = _strip_footer(_field(text, '(?:Registration )?Restrictions')) or ''
    # General Requirements may encode credit/standing logic and is not silently
    # substituted for a missing Prerequisites field.
    parsed = banner_expression(prereq)
    credits = re.search(r'(\d+(?:\.\d+)?)\s+Credit\s+hours?', text, re.I)
    ects = re.search(r'\b(\d+(?:\.\d+)?)\s+ECTS\b', text, re.I)
    return dict(code=cid, title=title or cid, catalogTerm=term, source=source,
        sourceRole='course-catalog', credits=numeric(credits[1]) if credits else None,
        ects=numeric(ects[1]) if ects else None, prerequisite=parsed,
        corequisite=banner_expression(coreq), prerequisiteText=prereq or '', corequisiteText=coreq or '',
        generalRequirements=general, restrictions=restrictions,
        scope='Official Banner catalog rules for ' + term_label(term))


def parse_schedule(html: str, cid: str, term: str, source: str):
    """Only the Dynamic Schedule can confirm section/CRN availability."""
    cid = code(cid)
    d = Document(html)
    _term_check(d, term)
    anchors = []
    for n in d.nodes:
        if n.tag != 'a':
            continue
        target = urljoin(source, unescape(n.attrs.get('href', '')))
        u = urlsplit(target); q = parse_qs(u.query)
        if u.hostname == 'suis.sabanciuniv.edu' and u.path == '/prod/bwckschd.p_disp_detail_sched':
            if q.get('term_in') != [term] or len(q.get('crn_in', [])) != 1 or not re.fullmatch(r'\d{5}', q['crn_in'][0]):
                raise CatalogError('Wrong term or malformed CRN in schedule results.')
            anchors.append((n.ancestor('th') or n, q['crn_in'][0], target, n.text()))
    if not anchors:
        if re.search(r'\bNo (?:classes|sections) were found\b|No classes match', d.text, re.I):
            return dict(code=cid, scheduleTerm=term, offered=False, sections=[], complete=True,
                        source=source, sourceRole='dynamic-schedule')
        raise CatalogError('No recognizable schedule sections; availability remains unknown.')
    sections = {}
    node_positions = [n.start for n in d.nodes]
    for i, (node, crn, url, label) in enumerate(anchors):
        if not re.search(r'\b' + re.escape(cid) + r'\b', label):
            raise CatalogError('Schedule returned a different course; no sections were attached.')
        stop = anchors[i+1][0].start if i+1 < len(anchors) else d.pos + 1
        meetings = []
        for table in d.nodes[bisect_left(node_positions, node.start):bisect_left(node_positions, stop)]:
            if table.tag != 'table' or not node.start < table.start < stop:
                continue
            rows = [r for r in table.all('tr') if not any(r.all('tr'))]
            if not rows:
                continue
            headers = [c.text() for c in rows[0].children if isinstance(c, Node) and c.tag in {'th', 'td'}]
            if not any(x.lower() == 'time' for x in headers) or not any('day' in x.lower() for x in headers):
                continue
            for row in rows[1:]:
                cells = [c.text() for c in row.children if isinstance(c, Node) and c.tag in {'th', 'td'}]
                if len(cells) == len(headers):
                    meetings.append(dict(zip(headers, cells)))
        sections[crn] = dict(crn=crn, label=label, source=url, meetings=meetings)
    return dict(code=cid, scheduleTerm=term, offered=True, sections=list(sections.values()),
                complete=True, source=source, sourceRole='dynamic-schedule')


class BannerAdapter:
    def __init__(self, read):
        # read(url, fields=None) returns decoded HTML and final verified URL.
        self.read = read

    def terms(self):
        html, final = self.read(CATALOG_START)
        return dict(terms=term_options(html), source=final, sourceRole='catalog-terms')

    def catalog(self, term):
        html, final = self.read(CATALOG_START)
        if term not in {x['id'] for x in term_options(html)}:
            raise CatalogError('The selected catalog term is not listed by the official source.')
        form, action = pick_form(html, final, 'bwckctlg.p_disp_cat_term_date')
        search, search_url = self.read(action, term_fields(form, term))
        form, action = pick_form(search, search_url, 'bwckctlg.p_display_courses')
        subject_select = next((n for n in form.all('select') if n.attrs.get('name') == 'sel_subj'), None)
        if subject_select is None:
            raise CatalogError('The subject selector was absent in the official search form.')
        subjects = list(dict.fromkeys(o.attrs.get('value', '') for o in subject_select.all('option')
                                    if re.fullmatch(r'[A-Z]{2,8}', o.attrs.get('value', ''))))
        # Read subjects from this semester, not the captured list of 74 forever.
        result, source = self.read(action, catalog_form(term, subjects))
        parsed = parse_entries(result, term, source)
        parsed['subjects'] = subjects
        return parsed

    def schedule(self, cid, term, links=()):
        results = []
        checked_links = []
        for link in dict.fromkeys(links):
            u = urlsplit(link); q = parse_qs(u.query)
            if (u.hostname == 'suis.sabanciuniv.edu' and u.path in {'/prod/bwckschd.p_get_crse_unsec','/prod/bwckschd.p_get_crse_unsec2'}
                    and q.get('term_in') == [term]):
                if len(checked_links) >= 12:
                    raise CatalogError('Too many schedule-type links for one course; no incomplete result was published.')
                html, final = self.read(link)
                results.append(parse_schedule(html, cid, term, final))
                checked_links.append(final)
        if results:
            merged = {}
            for result in results:
                for section in result['sections']:
                    if section['crn'] in merged and merged[section['crn']] != section:
                        raise CatalogError('Conflicting duplicate sections; previous schedule retained.')
                    merged[section['crn']] = section
            return dict(results[0], offered=bool(merged), sections=list(merged.values()), sources=checked_links)
        # Discover the search form if the catalog does not contain schedule links.
        html, final = self.read(SCHEDULE_START)
        if term not in {t['id'] for t in term_options(html)}:
            raise CatalogError('That semester is not listed in the Dynamic Schedule.')
        form, action = pick_form(html, final, 'bwckgens.p_proc_term_date')
        search, source = self.read(action, term_fields(form, term))
        options = [(form, url) for form, url in forms(search, source)
                   if urlsplit(url).path in {'/prod/bwckschd.p_get_crse_unsec','/prod/bwckschd.p_get_crse_unsec2'}]
        if len(options) != 1:
            raise CatalogError('Dynamic Schedule search form was not found.')
        form, action = options[0]
        subj, num = code(cid).split()
        fields = form_fields(form, {'term_in': term, 'sel_subj': subj, 'sel_crse': num})
        if not any(k == 'sel_crse' and v == num for k,v in fields):
            raise CatalogError('Dynamic Schedule did not expose the course-number field.')
        result, final = self.read(action, fields)
        return parse_schedule(result, cid, term, final)
