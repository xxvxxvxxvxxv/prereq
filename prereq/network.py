"""Fixed-origin HTTPS fetcher with robots checks, bounded bodies and no proxying."""
from __future__ import annotations
import http.client
import ipaddress
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit, parse_qsl, urljoin
from urllib.robotparser import RobotFileParser
from .catalog import CatalogError

USER_AGENT = 'SabanciPrereq/1.0 (public course catalog visualizer; no authentication)'
PATHS = {'/robots.txt'} | {
    f'/{prefix}/{endpoint}' for prefix in ('prod', 'HbbmInst') for endpoint in (
        'SU_DEGREE.p_select_term', 'SU_DEGREE.p_degree_detail',
        'SU_DEGREE.p_list_courses', 'sabanci_www.p_get_courses')}
KEYS = {'P_LANG','P_LEVEL','P_PROGRAM','P_SUBMIT','P_TERM','P_AREA',
        'crse_numb','lang','levl_code','subj_code'}

def validate_url(url: str) -> str:
    import re
    try:
        u = urlsplit(url)
        if (u.scheme != 'https' or u.hostname != 'suis.sabanciuniv.edu' or u.port not in (None,443)
            or u.username is not None or u.password is not None or u.fragment or u.path not in PATHS):
            raise CatalogError('Upstream URL is not allowed.')
        pairs = parse_qsl(u.query, keep_blank_values=True, strict_parsing=True)
        if len(pairs) > 8 or len(set(k for k,v in pairs)) != len(pairs):
            raise CatalogError('Invalid upstream parameters.')
        for k,v in pairs:
            if k not in KEYS or not re.fullmatch(r'[A-Za-z0-9_]{1,50}', v):
                raise CatalogError('Invalid upstream parameters.')
        if u.path == '/robots.txt' and u.query:
            raise CatalogError('Invalid robots URL.')
        return url
    except ValueError as exc:
        raise CatalogError('Upstream URL is not allowed.') from exc

class PinnedHTTPS(http.client.HTTPSConnection):
    """Resolve once, reject non-public addresses, keep TLS hostname verification."""
    def connect(self):
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise CatalogError('The upstream resolved to a non-public address.')
        error = None
        for _, _, _, _, address in addresses[:4]:
            try:
                sock = socket.create_connection((address[0], self.port), timeout=self.timeout)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except (OSError, ssl.SSLError) as exc:
                error = exc
        raise OSError('Could not connect to the official catalog.') from error

class OfficialClient:
    def __init__(self, offline=False):
        self.offline = offline
        self.lock = threading.Lock()
        self.last = 0.0
        self.robot = None
        self.robot_expiry = 0.0
        self.delay = 1.0
        self.backoff_until = 0.0
    def _request(self, url):
        for redirects in range(4):
            validate_url(url)
            wait = max(self.last + self.delay - time.monotonic(), 0)
            time.sleep(wait)
            self.last = time.monotonic()
            u = urlsplit(url)
            conn = PinnedHTTPS(u.hostname, timeout=10, context=ssl.create_default_context())
            try:
                conn.request('GET', u.path + ('?'+u.query if u.query else ''), headers={
                    'User-Agent': USER_AGENT, 'Accept': 'text/html,text/plain;q=0.8',
                    'Accept-Encoding': 'identity', 'Connection': 'close'})
                response = conn.getresponse()
                if response.status in {301,302,303,307,308}:
                    url = urljoin(url, response.getheader('Location',''))
                    validate_url(url)
                    continue
                if response.status in {429,503}:
                    try:
                        retry = min(max(int(response.getheader('Retry-After', '300')), 60), 86400)
                    except ValueError:
                        retry = 300
                    self.backoff_until = time.monotonic()+retry
                    raise CatalogError('The official catalog requested a pause. Cached data remains available.')
                if response.status != 200:
                    return response.status, '', url
                content_type = response.getheader('Content-Type','').lower()
                if not any(t in content_type for t in ('text/html','text/plain','application/xhtml+xml')):
                    raise CatalogError('Unexpected upstream content type.')
                length = response.getheader('Content-Length')
                if length and int(length) > 2_000_000:
                    raise CatalogError('Upstream page exceeds size limit.')
                parts, size, deadline = [], 0, time.monotonic()+25
                while True:
                    part = response.read(65536)
                    if not part:
                        break
                    size += len(part)
                    if size > 2_000_000 or time.monotonic() > deadline:
                        raise CatalogError('Upstream page exceeds resource limits.')
                    parts.append(part)
                charset = response.headers.get_content_charset() or 'utf-8'
                if charset.lower() not in {'utf-8','iso-8859-1','iso-8859-9','windows-1254','windows-1252','us-ascii'}:
                    charset = 'utf-8'
                return 200, b''.join(parts).decode(charset, errors='replace'), url
            finally:
                conn.close()
        raise CatalogError('Too many upstream redirects.')
    def get(self, url: str) -> tuple[str, str]:
        validate_url(url)
        if self.offline:
            raise CatalogError('Offline mode: live requests are disabled. Showing only exact matching snapshots.')
        # One upstream request at a time across the application, at most one per second.
        with self.lock:
            if time.monotonic() < self.backoff_until:
                raise CatalogError('Upstream cooldown is active. Try again later.')
            if self.robot is None or time.monotonic() >= self.robot_expiry:
                status, text, _ = self._request('https://suis.sabanciuniv.edu/robots.txt')
                rp = RobotFileParser()
                if status == 404:
                    rp.parse(['User-agent: *', 'Allow: /'])
                elif status == 200:
                    rp.parse(text.splitlines())
                else:
                    raise CatalogError('Could not verify the official site’s crawling policy. Live fetch paused.')
                self.robot = rp
                self.robot_expiry = time.monotonic()+86400
                self.delay = max(1.0, float(rp.crawl_delay('SabanciPrereq') or rp.crawl_delay('*') or 0))
                rate = rp.request_rate('SabanciPrereq') or rp.request_rate('*')
                if rate and rate.requests:
                    self.delay = max(self.delay, rate.seconds/rate.requests)
            if self.delay > 30:
                raise CatalogError('The site requests a long crawl interval. Live fetching is paused; use official source links.')
            if not self.robot.can_fetch('SabanciPrereq', url):
                raise CatalogError('Automated access is disallowed by the official site’s robots policy.')
            status, html, final = self._request(url)
            if status != 200:
                raise CatalogError(f'Official catalog returned HTTP {status}. No sign-in or access bypass attempted.')
            return html, final
