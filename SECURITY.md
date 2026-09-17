# Security and access behavior

This repair only changes the local PREREQ project. It has no GitHub API client, deployment action, university login flow, transcript upload, analytics, or user-cookie import. No operation modifies enrollment, grades or institutional records.

## Upstream access

Only HTTPS on `suis.sabanciuniv.edu`, `www.sabanciuniv.edu`, and `sabanciuniv.edu` is allowed. Routes are exact public catalog/degree/schedule endpoints, not arbitrary URLs. Form keys are allowlisted, values bounded, and duplicate fields are permitted only for known Banner array controls. POST is limited to public search forms.

DNS is resolved before connecting. Non-global/private IPs are rejected, and TLS verifies the original hostname. Redirects are revalidated. Login URLs and cross-host POST redirects are rejected. The client does not disable certificate verification, use proxies or copy browser credentials.

HTTP 401, 403, 429 and 503 trigger a pause. Password, CAPTCHA and recognized challenge responses are not parsed as catalog data. No challenge solving, user-agent masquerading or sign-in attempts are made. Anonymous cookies obtained from these public responses are held in a bounded, per-client in-memory jar; user-supplied cookies are not accepted.

The default `public-queries` fetch mode does not use robots.txt as an HTTP authorization check. It must not be represented as robots-compliant crawling or university-granted permission. The SUIS robots file excludes crawling. `PREREQ_FETCH_POLICY=robots` retains strict exclusion behavior for operators who select it. Actual access restrictions are respected in both modes. Review source terms and obtain an appropriate access arrangement before operating an unattended public collector.

## Resource bounds

At least 1.5 seconds between serialized source requests; default 45-second socket timeout; bounded response reading and 16 MB body cap; 32 KB encoded form cap. No unbounded decompression. Background indexing stops after three consecutive errors or its time budget. Cache and in-memory job/lock state are bounded. Responses do not execute upstream JavaScript.

## Data integrity

Catalog term, admission term and schedule term are separate. Missing fields stay unknown. A malformed or mismatched course/term response is rejected. Atomic SQLite snapshot writes preserve previous data after failure. A complete degree snapshot is not replaced with missing elective pools. Term-specific prerequisite keys never fall back to unversioned examples. Cached observation times are not advanced on failures.

## Browser/API

CSP restricts scripts and network access to the app origin. Source strings are inserted with textContent, not HTML. External links are limited to known official hosts. API calls require the same-origin client header, reject cross-site fetches, enforce query bounds and rate limits, and never offer a generic URL fetch endpoint. Refresh requires POST and validates Origin when present. Deployment hosts are explicitly allowlisted. Private files and cache paths are not served.

Local plans are keyed by program and admission term and are never sent to source sites. Import/export is bounded and validates shape, course syntax and status. An incomplete source refresh does not delete local markers.

Tests exercise these controls but are not an independent security audit. Live source behavior and production hosting were not verified by the local build checks.
