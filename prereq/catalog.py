"""Small, conservative adapters for public SUIS HTML. Never infer missing rules."""
from __future__ import annotations
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, parse_qs, urlencode
import re

HOST = 'https://suis.sabanciuniv.edu'
COURSE_RE = re.compile(r'^([A-Z]{2,8})\s*(\d{3,5}[A-Z]{0,2})$')
TERM_RE = re.compile(r'^(19\d{2}|20\d{2})0[123]$')
PROGRAMS = [
    ('BSEE', 'Electronics Engineering', 'EE', 'FENS'),
    ('BSCS', 'Computer Science and Engineering', 'CS', 'FENS'),
    ('BSDSA', 'Data Science and Analytics', 'DSA', 'FENS'),
    ('BSMS', 'Industrial Engineering', 'IE', 'FENS'),
    ('BSMAT', 'Materials Science and Nanoengineering', 'MAT', 'FENS'),
    ('BSME', 'Mechatronics Engineering', 'ME', 'FENS'),
    ('BSBIO', 'Molecular Biology, Genetics and Bioengineering', 'BIO', 'FENS'),
    ('BAECON', 'Economics', 'ECON', 'FASS'),
    ('BAPSIR', 'Political Science and International Relations', 'PSIR', 'FASS'),
    ('BAPSY', 'Psychology', 'PSY', 'FASS'),
    ('BAVACD', 'Visual Arts and Visual Communication Design', 'VACD', 'FASS'),
    ('BAMAN', 'Management', 'MAN', 'SBS'),
]
PROGRAM_MAP = {p[0]: dict(id=p[0], name=p[1], short=p[2], faculty=p[3]) for p in PROGRAMS}
CATEGORIES = {'University Courses': 'university', 'Required Courses': 'required',
              'Core Electives': 'core', 'Area Electives': 'area', 'Free Electives': 'free',
              'Faculty Courses': 'faculty', 'Engineering': 'engineering', 'Basic Science': 'basic'}
LABELS = {v: k for k, v in CATEGORIES.items()}

class CatalogError(ValueError):
    """Upstream page cannot safely be interpreted as the requested catalog."""

def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', s.replace('\xa0', ' ')).strip()

def code(value: str) -> str:
    m = COURSE_RE.fullmatch(value.strip().upper())
    if not m:
        raise CatalogError('Invalid course code.')
    return f'{m[1]} {m[2]}'

def term_label(term: str) -> str:
    if not TERM_RE.fullmatch(term):
        raise CatalogError('Invalid admission term.')
    return f'{["Fall", "Spring", "Summer"][int(term[-1])-1]} {term[:4]}–{int(term[:4])+1}'

def degree_url(program: str, term: str | None = None) -> str:
    if program not in PROGRAM_MAP:
        raise CatalogError('Unknown program.')
    # Management's published entry point uses the legacy HbbmInst route.
    route = 'HbbmInst' if program == 'BAMAN' and term is None else 'prod'
    params = dict(P_LANG='EN', P_LEVEL='UG', P_PROGRAM=program)
    endpoint = 'p_select_term'
    if term:
        term_label(term)
        params.update(P_SUBMIT='Select', P_TERM=term)
        endpoint = 'p_degree_detail'
    return f'{HOST}/{route}/SU_DEGREE.{endpoint}?{urlencode(params)}'

def course_url(value: str) -> str:
    subject, number = code(value).split()
    return f'{HOST}/prod/sabanci_www.p_get_courses?' + urlencode(dict(
        crse_numb=number, lang='eng', levl_code='UG', subj_code=subject))


def catalog_link(url: str) -> tuple[str, dict[str, list[str]]]:
    """Read an official link without changing its request URL.

    The university wrapper puts the operation inside the query, followed by a
    second question mark. Ordinary query normalization loses the first field
    or moves the operation. This is a parser only, not a network permission.
    """
    u = urlsplit(url)
    if u.scheme != 'https' or u.username is not None or u.password is not None:
        return '', {}
    try:
        if u.port not in (None, 443):
            return '', {}
    except ValueError:
        return '', {}
    operations = {'su_degree.p_select_term', 'su_degree.p_degree_detail',
                  'su_degree.p_list_courses', 'sabanci_www.p_get_courses'}
    if u.hostname == 'suis.sabanciuniv.edu':
        pieces = u.path.split('/')
        if len(pieces) != 3 or pieces[1] not in {'prod', 'HbbmInst'}:
            return '', {}
        operation, query = pieces[2].lower(), u.query
    elif u.hostname in {'www.sabanciuniv.edu', 'sabanciuniv.edu'} and u.path == '/en/prospective-students/degree-detail':
        operation, separator, query = u.query.partition('?')
        # Some HTML encoders encode the nested question mark. Decode only that
        # delimiter, never an entire query and its parameter values twice.
        if not separator:
            marker = re.search(r'%3f', u.query, re.I)
            if not marker:
                return '', {}
            operation, query = u.query[:marker.start()], u.query[marker.end():]
        operation = operation.lower()
    else:
        return '', {}
    if operation not in operations:
        return '', {}
    try:
        params = parse_qs(query, keep_blank_values=True, max_num_fields=12,
                          strict_parsing=True)
    except ValueError as exc:
        raise CatalogError('Malformed official catalog link.') from exc
    if any(len(values) != 1 for values in params.values()):
        raise CatalogError('Duplicate fields in an official catalog link.')
    return operation, params

@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: Node | None = None
    start: int = 0
    end: int = 0
    def text(self) -> str:
        return clean(' '.join(c.text() if isinstance(c, Node) else c for c in self.children))
    def all(self, tag: str | None = None):
        for c in self.children:
            if isinstance(c, Node):
                if tag is None or c.tag == tag:
                    yield c
                yield from c.all(tag)
    def ancestor(self, tag: str):
        n = self.parent
        while n:
            if n.tag == tag:
                return n
            n = n.parent
        return None

class Document(HTMLParser):
    VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr', 'source', 'area', 'base', 'embed'}
    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
        self.pos = 0
        self.nodes: list[Node] = []
        self.tokens: list[tuple[int, str]] = []
        self.feed(html)
        for n in self.stack:
            n.end = self.pos + 1
    def handle_starttag(self, tag, attrs):
        # Old Banner HTML sometimes leaves table cells and rows implicitly closed.
        if tag in {'td', 'th', 'tr'}:
            close = {'td', 'th'} if tag in {'td', 'th'} else {'td', 'th', 'tr'}
            while self.stack[-1].tag in close:
                self.stack.pop().end = self.pos
        self.pos += 1
        if len(self.nodes) > 250000 or len(self.stack) > 120:
            raise CatalogError('Catalog HTML exceeds structural limits.')
        n = Node(tag, dict(attrs), parent=self.stack[-1], start=self.pos, end=self.pos+1)
        n.parent.children.append(n)
        self.nodes.append(n)
        if tag not in self.VOID:
            self.stack.append(n)
        else:
            n.children.append(' ')
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                for n in self.stack[i:]:
                    n.end = self.pos + 1
                self.stack = self.stack[:i]
                break
    def handle_data(self, data):
        self.pos += 1
        if not any(n.tag in {'script', 'style', 'noscript'} for n in self.stack):
            self.stack[-1].children.append(data)
            self.tokens.append((self.pos, data))
    @property
    def text(self):
        return self.root.text()

def category(text: str) -> str | None:
    text = clean(text).lower()
    exact = next((v for k, v in CATEGORIES.items() if text == k.lower()), None)
    if exact:
        return exact
    for prefix, key in [('core elective', 'core'), ('area elective', 'area'), ('free elective', 'free')]:
        if re.fullmatch(re.escape(prefix) + r'(?:s)?(?:\s+(?:[IVX]+|[0-9]+))?(?:\s*\([^)]*\))?', text, re.I):
            return key
    return None

def numeric(value: str):
    return float(value) if '.' in value else int(value)

def parse_terms(html: str, program: str) -> list[dict]:
    d = Document(html)
    terms = set()
    for n in d.nodes:
        if n.tag == 'option':
            value = n.attrs.get('value', '')
            if TERM_RE.fullmatch(value):
                terms.add(value)
        if n.tag == 'a':
            _, q = catalog_link(n.attrs.get('href', ''))
            p = q.get('P_PROGRAM', [program])[0]
            t = q.get('P_TERM', [''])[0]
            if p == program and TERM_RE.fullmatch(t):
                terms.add(t)
    if not terms:
        raise CatalogError('No admission terms found. The catalog format or access policy may have changed.')
    return [dict(id=t, label=term_label(t)) for t in sorted(terms, reverse=True)]

def course_row(row: Node, source: str) -> dict | None:
    links = []
    for a in row.all('a'):
        href = urljoin(source, a.attrs.get('href', ''))
        operation, params = catalog_link(href)
        if operation == 'sabanci_www.p_get_courses':
            q = {k.lower(): v[0] for k, v in params.items()}
            try:
                cid = code(q.get('subj_code', '') + q.get('crse_numb', ''))
            except CatalogError:
                continue
            links.append((a, href, cid))
    if not links:
        if any(isinstance(c, Node) and c.tag in {'td','th'} and COURSE_RE.fullmatch(c.text()) for c in row.children):
            raise CatalogError('A course row has no readable official course link.')
        return None
    cid = links[0][2]
    if len({a[2] for a in links}) != 1:
        return None  # A wrapper row, not one course.
    cells = [clean(c.text()) for c in row.children if isinstance(c, Node) and c.tag in {'td', 'th'}]
    title = next((a.text() for a, _, _ in links if a.text() and a.text() != cid and not COURSE_RE.fullmatch(a.text())), '')
    # Read the numerical cells, not digits embedded in a title or course number.
    nums = [numeric(x) for x in cells if re.fullmatch(r'\d{1,3}(?:\.\d+)?', x)]
    faculty = next((x for x in reversed(cells) if x in {'FENS', 'FASS', 'SBS', 'SOM', 'SL'}), None)
    if not title:
        for i, cell in enumerate(cells):
            if clean(cell).replace(' ', '') == cid.replace(' ', '') and i+1 < len(cells):
                title = cells[i+1]
                break
    if not title or len(nums) < 2 or faculty is None:
        raise CatalogError(f'Could not read the title/credits/faculty for {cid}. Snapshot not replaced.')
    if any(x > 120 for x in nums[:2]):
        raise CatalogError('Unexpected course credit value.')
    return dict(code=cid, title=title, ects=nums[0], credits=nums[1], faculty=faculty,
                facultyCourse='*' in (cells[0] if cells else ''), source=links[0][1], poolSource=source)

def leaf_rows(d: Document):
    return [n for n in d.nodes if n.tag == 'tr' and not any(n.all('tr'))]

def parse_pool(html: str, program: str, source: str) -> list[dict]:
    d = Document(html)
    if not re.search(r'\(\s*' + re.escape(program) + r'\s*\)', d.text):
        raise CatalogError('The pool does not identify the requested program.')
    result = {}
    for r in leaf_rows(d):
        course = course_row(r, source)
        if course:
            if course['code'] in result and result[course['code']] != course:
                raise CatalogError('Conflicting duplicate course records.')
            result[course['code']] = course
    if not result or len(result) > 5000:
        raise CatalogError('Empty or unexpectedly large elective pool; retaining previous data.')
    return sorted(result.values(), key=lambda c: c['code'])

def parse_degree(html: str, program: str, term: str, source: str) -> dict:
    d = Document(html)
    if not re.search(r'\(\s*' + re.escape(program) + r'\s*\)', d.text):
        raise CatalogError('The degree page does not match the selected major.')
    expected = term_label(term).replace('–', '-')
    match = re.search(r'Admit\s+Term\s*:\s*(Fall|Spring|Summer)\s+(\d{4})\s*[-–/]\s*(\d{4})', d.text, re.I)
    if not match or f'{match[1].title()} {match[2]}-{match[3]}' != expected:
        raise CatalogError('The degree page does not confirm the selected admission term.')
    main_node = next(iter(d.root.all('main')), None)
    content_end = main_node.end if main_node else d.pos + 1
    rows = [r for r in leaf_rows(d) if main_node is None or main_node.start < r.start < content_end]
    summary, total, summary_end = [], {}, 0
    for row in rows:
        cells = [c.text() for c in row.children if isinstance(c, Node) and c.tag in {'td', 'th'}]
        # Read every numeric summary row, including program-specific requirements.
        if len(cells) != 4 or not cells[0] or not all(re.fullmatch(r'(?:\d+(?:\.\d+)?|[-—–]?)', x.strip()) for x in cells[-3:]):
            continue
        vals = [numeric(x) if re.fullmatch(r'\d+(?:\.\d+)?', x) else None for x in cells[-3:]]
        entry = dict(label=cells[0], ects=vals[0], credits=vals[1], courses=vals[2])
        if cells[0].lower() == 'total':
            total, summary_end = entry, row.end
            break
        summary.append(entry)
    if not total or not total.get('credits') or not total.get('ects') or len(summary) > 30:
        raise CatalogError('Degree totals not found; refusing a partial parse.')
    labels = {x['label'].lower(): x['label'] for x in summary}
    labels.update({k.lower(): k for k in CATEGORIES if category(k) in {'faculty','engineering','basic'}})
    headings = []
    for n in d.nodes:
        if n.start < summary_end or n.start >= content_end or n.tag not in {'h1','h2','h3','h4','b','strong','p','td','div','font','a'}:
            continue
        label = labels.get(n.text().lower())
        if label and not (n.tag == 'a' and n.attrs.get('href')):
            if not any(h[1] == label and h[0] <= n.start < h[2] for h in headings):
                headings.append((n.start, label, n.end))
    headings.sort()
    main = ('university','required','core','area','free')
    for entry in summary:
        cat = category(entry['label'])
        if cat in {'faculty','engineering','basic'}:
            continue
        if not any(h[1] == entry['label'] for h in headings):
            raise CatalogError(f"Section not found: {entry['label']}. Snapshot not replaced.")
    if not any(category(h[1]) == 'university' for h in headings):
        raise CatalogError('University requirement section was not found; parser update needed.')
    specs, pools, notes = [], {}, []
    for i, (start, label, end) in enumerate(headings):
        cat = category(label) or 'additional'
        stop = headings[i+1][0] if i+1 < len(headings) else content_end
        relevant_rows = [r for r in rows if start < r.start < stop]
        courses = []
        used_rows = []
        for row in relevant_rows:
            c = course_row(row, source)
            if c:
                courses.append(c)
                used_rows.append(row)
        chunks = []
        def text_between(n):
            if n.tag in {'thead', 'script', 'style'}:
                return
            if n.end <= end or n.start >= stop or any(r.start <= n.start < r.end for r in used_rows):
                return
            for child in n.children:
                if isinstance(child, Node):
                    text_between(child)
                elif n.start >= end and n.end <= stop and n.tag not in {'script','style'}:
                    chunks.append(child)
        text_between(d.root)
        rule = clean(' '.join(chunks))
        if len(rule) > 14000:
            raise CatalogError('Unusually large degree rule; refusing to truncate it.')
        if rule:
            notes.append(dict(label=label, text=rule))
        if cat in {'faculty','engineering','basic'}:
            continue
        same = [h for h in headings if (category(h[1]) or 'additional') == cat]
        sid = cat if len(same) == 1 and cat != 'additional' else f'{cat}-{i}'
        spec = dict(id=sid, category=cat, label=label, courses=courses, rule=rule, source=source,
                    minimum=next((x for x in summary if x['label'] == label), {}))
        for a in d.nodes:
            if a.tag != 'a' or not start < a.start < stop:
                continue
            href = urljoin(source, a.attrs.get('href', ''))
            operation, q = catalog_link(href)
            if operation == 'su_degree.p_list_courses':
                if q.get('P_PROGRAM', [''])[0] != program or q.get('P_TERM', [''])[0] != term:
                    raise CatalogError('Elective link points to another major or admission term.')
                if sid in pools and pools[sid] != href:
                    raise CatalogError('Multiple links within one requirement need an adapter review.')
                pools[sid] = href
        if not courses and sid not in pools and spec['minimum'].get('credits') != 0:
            raise CatalogError(f'No course list found for {label}.')
        specs.append(spec)
    # Preserve split core pools and extra requirements, never fold them into a mandatory list.
    sections = []
    for cat in main:
        parts = [s for s in specs if s['category'] == cat]
        if not parts:
            sections.append(dict(id=cat, category=cat, label=LABELS[cat], courses=[],
                rule='This category is not listed in this degree requirement summary.',
                source=source, complete=True, dataStatus='not-applicable',
                minimum=dict(credits=0), notApplicable=True))
        elif len(parts) == 1:
            sections.append(parts[0])
        else:
            merged = {c['code']: c for part in parts for c in part['courses']}
            sections.append(dict(id=cat, category=cat, label=LABELS[cat], courses=list(merged.values()),
                rule=' '.join(p['label'] + ': ' + p['rule'] for p in parts), source=source, subsections=parts))
    sections.extend(s for s in specs if s['category'] == 'additional')
    return dict(schemaVersion=1, program=PROGRAM_MAP[program], term=term, termLabel=term_label(term),
                summary=summary, total=total, sections=sections, notes=notes,
                source=source, poolLinks=pools, warnings=[
                    'Course pools are choices, not a list of courses you must all complete.',
                    'Program-specific and overlapping requirements are preserved as source rules, not automatically audited.'])

def parse_expression(raw: str | None) -> dict:
    if raw is None or not clean(raw):
        return dict(type='unknown', raw=raw or '', reason='No readable requirement field.')
    raw = clean(raw)
    if raw.lower() in {'__', '_', '-', 'none', 'no prerequisites', 'no prerequisite', 'n/a'}:
        return dict(type='none', raw=raw)
    # Recognize only an explicit grammar. Ambiguous text is never converted to "none".
    token = re.compile(r'\s*(?:(?P<course>[A-Z]{2,8}\s*\d{3,5}[A-Z]{0,2})(?:\s*-\s*Undergraduate\s*-\s*Min\s+Grade\s+(?P<grade>[A-Z][+-]?))?|(?P<op>and\b|or\b)|(?P<paren>[()]))', re.I)
    items, pos = [], 0
    while pos < len(raw):
        m = token.match(raw, pos)
        if not m or len(items) > 150:
            return dict(type='unknown', raw=raw, reason='Contains a condition needing manual review.')
        if m['course']:
            items.append(dict(type='course', code=code(m['course']), minGrade=m['grade'].upper() if m['grade'] else None))
        else:
            items.append((m['op'] or m['paren']).lower())
        pos = m.end()
    idx = 0
    def atom(depth=0):
        nonlocal idx
        if idx >= len(items) or depth > 20:
            raise ValueError()
        item = items[idx]; idx += 1
        if isinstance(item, dict):
            return item
        if item == '(':
            result = expr('or', depth+1)
            if idx >= len(items) or items[idx] != ')':
                raise ValueError()
            idx += 1
            return result
        raise ValueError()
    def expr(op, depth=0):
        nonlocal idx
        read = (lambda: expr('and', depth)) if op == 'or' else (lambda: atom(depth))
        children = [read()]
        while idx < len(items) and items[idx] == op:
            idx += 1
            children.append(read())
        return children[0] if len(children) == 1 else dict(type=op, children=children)
    try:
        result = expr('or')
        if idx != len(items):
            raise ValueError()
        return result
    except (ValueError, RecursionError):
        return dict(type='unknown', raw=raw, reason='Unrecognized or incomplete prerequisite expression.')

def parse_course(html: str, cid: str, source: str) -> dict:
    cid = code(cid)
    text = Document(html).text
    title_match = re.search(re.escape(cid) + r'\s+(.{1,500}?)\s+(\d+(?:\.\d+)?)\s+Credits?\b', text, re.I)
    if not title_match:
        raise CatalogError('Course identity or credit heading not found.')
    fields = {}
    for name in ('Prerequisite', 'Corequisite', 'ECTS Credit', 'General Requirements'):
        m = re.search(r'\b' + name + r'\s*:\s*(.*?)(?=\b(?:Prerequisite|Corequisite|ECTS Credit|General Requirements)\s*:|$)', text, re.I)
        fields[name] = clean(m[1]) if m else None
    if any(value is not None and len(value) > 15000 for value in fields.values()):
        raise CatalogError('Unusually large course requirement field.')
    if fields['Prerequisite'] is None or fields['Corequisite'] is None:
        raise CatalogError('Requirement fields missing; not treating them as empty.')
    ects = re.search(r'^(\d+(?:\.\d+)?)\s+ECTS', fields['ECTS Credit'] or '')
    prerequisite = parse_expression(fields['Prerequisite'])
    description = text[title_match.end():].split('Last Offered Terms', 1)[0]
    contextual = re.search(r'(?:program[ -]specific|admission[ -]year|prerequisite requirements|completed.{0,25}credits)', description, re.I)
    general = fields['General Requirements'] or ''
    if contextual:
        general = (general + ' Additional program, credit or cohort conditions appear in the course description. Check the official page.').strip()
        if prerequisite['type'] == 'none':
            prerequisite = dict(type='unknown', raw=fields['Prerequisite'], reason='Context-dependent conditions in the course description; no universal prerequisite is inferred.')
    return dict(code=cid, title=title_match[1], credits=numeric(title_match[2]),
                ects=numeric(ects[1]) if ects else None, source=source,
                prerequisite=prerequisite, corequisite=parse_expression(fields['Corequisite']),
                prerequisiteText=fields['Prerequisite'], corequisiteText=fields['Corequisite'],
                generalRequirements=general, creditDistribution=fields['ECTS Credit'] or '',
                scope='Current course catalog, not a historical prerequisite snapshot for the admission term.')
