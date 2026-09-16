"""Single-process production server; upstream pacing is shared by its threads.

Render provides PORT. A Docker container defaults to 8000. TLS is terminated by
Render/the reverse proxy; PREREQ_PUBLIC_SCHEME=https pins browser Origin checks.
Never use start.py as a public production server.
"""
import os

port = int(os.environ.get("PORT", "8000"))
if not 1 <= port <= 65535:
    raise ValueError("PORT must be between 1 and 65535")
bind = f"0.0.0.0:{port}"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 90
graceful_timeout = 30
keepalive = 5
preload_app = False
worker_tmp_dir = "/tmp"
# Do not trust arbitrary public forwarded headers. The app uses a pinned public
# scheme instead; add only verified proxy IPs for other hosting environments.
forwarded_allow_ips = "127.0.0.1,::1"
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 4096
accesslog = "-"
errorlog = "-"
loglevel = "info"
# Avoid logging visitor IPs, query strings, referrers or browser identifiers.
access_log_format = '%(t)s "%(m)s %(U)s" %(s)s %(L)s'
