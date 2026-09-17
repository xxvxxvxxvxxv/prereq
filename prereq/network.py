"""Bounded public-catalog requests. No credentials, generic proxy, or login routes.

The default is targeted public queries initiated by PREREQ use, not a search
engine crawl. Set PREREQ_FETCH_POLICY=robots to opt into the robots exclusion
protocol as well. Actual HTTP access refusals always stop requests. Neither
mode bypasses authentication, TLS, IP controls, or a challenge page.
"""
from __future__ import annotations
from collections import Counter
import http.client
from http.cookies import SimpleCookie
import ipaddress
import os
import re
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit, parse_qsl, urljoin, urlencode
from urllib.robotparser import RobotFileParser
from .catalog import CatalogError, catalog_link

USER_AGENT = 'PREREQ/2.2 (public academic catalog reader; no authentication)'
OFFICIAL_HOSTS = {'suis.sabanciuniv.edu', 'www.sabanciuniv.edu', 'sabanciuniv.edu'}
WRAPPER_PATH = '/en/prospective-students/degree-detail'
DEGREE_OPERATIONS = ('SU_DEGREE.p_select_term', 'SU_DEGREE.p_degree_detail',
                     'SU_DEGREE.p_list_courses', 'sabanci_www.p_get_courses')
BANNER_OPERATIONS = ('bwckctlg.p_disp_dyn_ctlg', 'bwckctlg.p_disp_cat_term_date',
                     'bwckctlg.p_display_courses', 'bwckctlg.p_disp_course_detail',
                     'bwckschd.p_disp_dyn_sched', 'bwckgens.p_proc_term_date',
                     'bwckschd.p_get_crse_unsec', 'bwckschd.p_get_crse_unsec2',
                     'bwckschd.p_disp_detail_sched')
PATHS = {'/robots.txt'} | {f'/{prefix}/{op}' for prefix in ('prod', 'HbbmInst') for op in DEGREE_OPERATIONS}
PATHS |= {'/prod/' + op for op in BANNER_OPERATIONS}
DEGREE_KEYS = {'P_LANG', 'P_LEVEL', 'P_PROGRAM', 'P_SUBMIT', 'P_TERM', 'P_AREA',
               'P_FAC', 'coll_code', 'crse_numb', 'lang', 'levl_code', 'subj_code'}
BANNER_KEYS = {'term_in', 'cat_term_in', 'p_term', 'p_term_in', 'p_calling_proc', 'call_proc_in', 'subj_code_in', 'crse_numb_in',
               'sel_subj', 'sel_levl', 'sel_schd', 'sel_coll', 'sel_divs', 'sel_dept',
               'sel_attr', 'sel_crse_strt', 'sel_crse_end', 'sel_title', 'sel_from_cred',
               'sel_to_cred', 'sel_crse', 'crn_in', 'crse_numb', 'subj_code',
               'begin_hh', 'begin_mi', 'begin_ap', 'end_hh', 'end_mi', 'end_ap',
               'sel_day', 'sel_insm', 'sel_camp', 'sel_sess', 'sel_instr', 'sel_ptrm',
               'sel_open', 'rsts', 'path', 'schd_in', 'crse_in', 'search', 'SUB_BTN'}
# Public Banner forms represent multiselects with repeated keys (including a
# hidden dummy value). A dict would silently lose almost all subjects.
REPEATED = {k for k in BANNER_KEYS if k.startswith('sel_')}
POST_PATHS = {'/prod/' + x for x in ('bwckctlg.p_disp_cat_term_date',
              'bwckctlg.p_display_courses', 'bwckgens.p_proc_term_date',
              'bwckschd.p_get_crse_unsec', 'bwckschd.p_get_crse_unsec2')}
MAX_BODY = 16_000_000
MAX_FORM = 32_000


def _validate_fields(pairs, allowed, repeat=False):
    if len(pairs) > 512:
        raise CatalogError('Too many upstream form fields.')
    counts = Counter(k for k, _ in pairs)
    if any(n > 1 and (not repeat or k not in REPEATED) for k, n in counts.items()):
        raise CatalogError('Duplicate upstream parameter is not allowed.')
    for k, v in pairs:
        if k not in allowed or not isinstance(v, str) or len(v) > 180 or not re.fullmatch(r"[A-Za-z0-9_ .%:/,+()\-]*", v):
            raise CatalogError('Invalid upstream parameters.')
        if k in {'call_proc_in','p_calling_proc'} and v not in {'bwckctlg.p_disp_dyn_ctlg', 'bwckschd.p_disp_dyn_sched'}:
            raise CatalogError('Unrecognized Banner form action.')
    if len(urlencode(pairs).encode('ascii')) > MAX_FORM:
        raise CatalogError('Upstream form exceeds size limit.')


def validate_url(url: str) -> str:
    """Exact hosts and read-only public routes, preserving nested-query order."""
    try:
        u = urlsplit(url)
        if (u.scheme != 'https' or u.hostname not in OFFICIAL_HOSTS or u.port not in (None, 443)
                or u.username is not None or u.password is not None or u.fragment
                or len(url) > 32000 or any(c in url for c in ('\r', '\n', '\\'))):
            raise CatalogError('Upstream URL is not allowed.')
        if u.path == '/robots.txt':
            if u.query:
                raise CatalogError('Invalid robots URL.')
            return url
        if u.hostname != 'suis.sabanciuniv.edu':
            if u.path != WRAPPER_PATH:
                raise CatalogError('Upstream URL is not allowed.')
            operation, params = catalog_link(url)
            if not operation:
                raise CatalogError('Unrecognized official degree link.')
            _validate_fields([(k, v[0]) for k, v in params.items()], DEGREE_KEYS)
        else:
            if u.path not in PATHS:
                raise CatalogError('Upstream URL is not allowed.')
            pairs = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True, max_num_fields=512)
            banner = u.path.rsplit('/', 1)[-1] in BANNER_OPERATIONS
            _validate_fields(pairs, BANNER_KEYS if banner else DEGREE_KEYS, banner)
        return url
    except ValueError as exc:
        raise CatalogError('Upstream URL is not allowed.') from exc


class PinnedHTTPS(http.client.HTTPSConnection):
    """Resolve once; connect to that public address with verified hostname TLS."""
    def connect(self):
        try:
            addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise CatalogError(f'DNS lookup failed for {self.host}. No catalog response was received.') from exc
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise CatalogError('The upstream resolved to a non-public address.')
        error = None
        deadline = time.monotonic() + self.timeout
        for family, kind, proto, _, address in addresses[:4]:
            sock = socket.socket(family, kind, proto)
            try:
                remaining = deadline-time.monotonic()
                if remaining <= 0: raise socket.timeout('Connection deadline exceeded.')
                sock.settimeout(remaining)
                sock.connect(address)
                sock.settimeout(max(.1,deadline-time.monotonic()))
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except (OSError, ssl.SSLError) as exc:
                sock.close()
                error = exc
        raise CatalogError('Could not connect securely to the official catalog.') from error


class OfficialClient:
    def __init__(self, offline=False, policy=None):
        self.offline = offline
        self.lock = threading.RLock()
        self.last = 0.0
        self.robot = None
        self.robot_expiry = 0.0
        self.delay = 1.5
        self.backoff_until = 0.0
        self.policy = policy or os.environ.get('PREREQ_FETCH_POLICY', 'public-queries')
        if self.policy not in {'public-queries', 'robots'}:
            raise ValueError('PREREQ_FETCH_POLICY must be public-queries or robots.')
        self.timeout = min(120, max(15, int(os.environ.get('PREREQ_SOURCE_TIMEOUT', '45'))))
        self.cookies = {}  # Anonymous cookies obtained by this client only.
        self.robots = {}

    def _request(self, url, method='GET', fields=None):
        if method not in {'GET', 'POST'}:
            raise CatalogError('Only public read queries are supported.')
        validate_url(url)
        if method == 'POST':
            if urlsplit(url).hostname != 'suis.sabanciuniv.edu' or urlsplit(url).path not in POST_PATHS:
                raise CatalogError('This endpoint does not accept a public search POST.')
            _validate_fields(fields or [], BANNER_KEYS, True)
            body = urlencode(fields or []).encode('ascii')
        else:
            if fields is not None:
                raise CatalogError('GET request must not have a body.')
            body = None
        deadline = time.monotonic() + max(90, self.timeout * 2)
        for redirects in range(4):
            validate_url(url)
            wait = max(self.last + self.delay - time.monotonic(), 0)
            time.sleep(wait)
            self.last = time.monotonic()
            if self.last >= deadline:
                raise CatalogError('Official catalog exceeded the request deadline.')
            u = urlsplit(url)
            conn = PinnedHTTPS(u.hostname, timeout=min(self.timeout, deadline-self.last), context=ssl.create_default_context())
            headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html,text/plain;q=0.8',
                       'Accept-Encoding': 'identity', 'Connection': 'close'}
            if body is not None:
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
            if self.cookies.get(u.hostname):
                headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in self.cookies[u.hostname].items())
            try:
                conn.request(method, u.path + ('?' + u.query if u.query else ''), body=body, headers=headers)
                response = conn.getresponse()
                for key, value in response.getheaders():
                    if key.lower() == 'set-cookie' and len(value) < 4096:
                        try:
                            parsed = SimpleCookie(); parsed.load(value)
                            jar = self.cookies.setdefault(u.hostname, {})
                            for ck, cv in parsed.items():
                                if len(jar) < 32 and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', ck):
                                    jar[ck] = cv.coded_value
                        except Exception:
                            pass
                if response.status in {301, 302, 303, 307, 308}:
                    target = urljoin(url, response.getheader('Location', ''))
                    validate_url(target)
                    if body is not None and urlsplit(target).hostname != u.hostname:
                        raise CatalogError('Search POST redirected to another host; request stopped.')
                    if method == 'POST' and response.status in {301, 302, 303}:
                        method, body = 'GET', None
                    url = target
                    continue
                if response.status in {401, 403, 429, 503}:
                    try:
                        retry = min(max(int(response.getheader('Retry-After', '300')), 60), 86400)
                    except ValueError:
                        retry = 300
                    self.backoff_until = time.monotonic() + retry
                    raise CatalogError(f'Official source returned HTTP {response.status}. Requests paused; no access bypass attempted.')
                if response.status != 200:
                    return response.status, '', url
                content_type = response.getheader('Content-Type', '').lower()
                if not any(t in content_type for t in ('text/html', 'text/plain', 'application/xhtml+xml')):
                    raise CatalogError('Unexpected upstream content type.')
                length = response.getheader('Content-Length')
                if length and int(length) > MAX_BODY:
                    raise CatalogError('Upstream page exceeds the 16 MB response limit.')
                if response.getheader('Content-Encoding', 'identity').lower() not in {'', 'identity'}:
                    raise CatalogError('Unexpected compressed response; no unbounded decompression attempted.')
                parts, size = [], 0
                while True:
                    part = response.read(65536)
                    if not part:
                        break
                    size += len(part)
                    if size > MAX_BODY or time.monotonic() > deadline:
                        raise CatalogError('Upstream page exceeds response limits.')
                    parts.append(part)
                    if conn.sock:
                        conn.sock.settimeout(max(0.1, min(self.timeout, deadline-time.monotonic())))
                charset = response.headers.get_content_charset() or 'utf-8'
                if charset.lower() not in {'utf-8', 'iso-8859-1', 'iso-8859-9', 'windows-1254', 'windows-1252', 'us-ascii'}:
                    charset = 'utf-8'
                html = b''.join(parts).decode(charset, errors='replace')
                if re.search(r'(?:cf-chl-|g-recaptcha|hcaptcha|type=[\"\']password)', html, re.I):
                    self.backoff_until = time.monotonic() + 300
                    raise CatalogError('Official source returned a sign-in or verification page. Request stopped.')
                return 200, html, url
            except (socket.timeout, TimeoutError) as exc:
                raise CatalogError(f'Official source did not respond within {self.timeout} seconds. The previous snapshot was kept.') from exc
            finally:
                conn.close()
        raise CatalogError('Too many upstream redirects.')

    def _check_policy(self, url):
        if self.policy != 'robots':
            return
        u = urlsplit(url)
        cached = self.robots.get(u.hostname)
        if not cached or time.monotonic() >= cached[1]:
            status, text, _ = self._request('https://' + u.hostname + '/robots.txt')
            rp = RobotFileParser()
            if status == 404:
                rp.parse(['User-agent: *', 'Allow: /'])
            elif status == 200:
                rp.parse(text.splitlines())
            else:
                raise CatalogError('Could not verify the official site crawling policy.')
            self.robots[u.hostname] = rp, time.monotonic() + 86400
            self.robot = rp
            self.robot_expiry = self.robots[u.hostname][1]
        else:
            rp = cached[0]
        self.delay = max(self.delay, float(rp.crawl_delay('PREREQ') or rp.crawl_delay('*') or 0))
        if not rp.can_fetch('PREREQ', url):
            raise CatalogError('Robots-respecting mode: this source disallows crawling. No request sent.')

    def query(self, url, method='GET', fields=None):
        validate_url(url)
        if self.offline:
            raise CatalogError('Offline mode: no external requests are sent.')
        with self.lock:
            if time.monotonic() < self.backoff_until:
                raise CatalogError('Official source cooldown is active. Cached data remains available.')
            self._check_policy(url)
            if self.delay > 30:
                raise CatalogError('The source requests a long interval; fetching paused.')
            status, html, final = self._request(url, method, fields)
            if status != 200:
                raise CatalogError(f'Official catalog returned HTTP {status}. No sign-in attempted.')
            return html, final

    def get(self, url):
        return self.query(url)

    def post(self, url, fields):
        return self.query(url, 'POST', fields)
