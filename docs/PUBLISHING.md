# Local repair boundary

This package has not been uploaded or deployed. No GitHub workflow or publishing script is included. Do not interpret a local test report as proof of production source access.

Use `python3 start.py` to run locally, or `python3 start.py --offline` for no external requests. The complete source, tests and existing server configuration are included for inspection. `preview.html` is a static offline example only.

The retained Render/Docker/Gunicorn configuration is passive until an operator independently chooses to deploy it. This build does not call hosting or account APIs. Reusing an existing SQLite cache is supported; term-specific course keys cannot accidentally pick up old unversioned records.

`python3 scripts/check_live.py` uses the production adapters for a bounded anonymous source check and records failures precisely. No saved plans, passwords or user cookies are transmitted. The build environment's check failed at DNS resolution, so this package is not labeled fully live-verified.
