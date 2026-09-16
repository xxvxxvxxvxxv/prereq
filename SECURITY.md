# Security and privacy

This is a public-catalog reader and local planning UI, not a SUIS login client. It never requests a university username, password, transcript or token. It does not submit CRNs, request seats, bypass permission checks or register courses.

## Implemented controls

The upstream fetcher has one fixed HTTPS host and an explicit list of public paths and parameter names. It validates every redirect, rejects credentials and custom ports, checks DNS addresses against non-public ranges, pins the connection to the resolved public address, and retains TLS certificate/hostname verification. The public API accepts major, term or course code, never a user-provided destination URL.

Upstream traffic is serialized, normally at most one request per second. The reader respects robots directives, requests identity encoding, limits responses to 2 MB and structural HTML depth/node counts, bounds connect/read work, obeys rate-limit cooldowns, and does not retry around authentication or access restrictions. If robots cannot be checked, live reads pause.

Degree replacement is atomic after successful parsing of all referenced pools. Major/admission identity, summary totals, categories, course fields and elective links are checked. Unexpected pool shrinkage over 25% retains the previous snapshot for review. Rules that cannot be understood remain source text or explicit unknown conditions. None of these checks guarantees perfect extraction from arbitrary future HTML changes.

The local server binds to loopback. The WSGI application restricts Host values, serves only an explicit static-file map, and uses a restrictive Content Security Policy, no-sniff, no-referrer and anti-framing headers. Browser API calls require a custom header, cross-site requests are refused, no cross-origin API access is enabled, and refresh is POST-only with an Origin check. Rate tracking, refresh jobs, cache entries, field lengths, plan imports and JSON bodies are bounded. A single prerequisite-index job runs at a time, uses at most 1,500 target codes, stops after three consecutive source failures or 20 minutes, and uses the same paced client as on-demand reads. These are abuse-reduction controls, not authentication for the public catalog.

All remote strings are rendered through text nodes, never remote HTML insertion. Imported plans must match the exact selected major/term and contain only known course codes with allowed status values. No file is executed during import.

## Data and logs

Planned/Completed marks and last selection are stored in browser localStorage. Plan JSON export is user-initiated. No analytics or external frontend resources are loaded. Browser storage is not encrypted and is not an authenticated vault; anyone using the same browser profile can see its plan.

The server necessarily sees requested course codes, requested degree keys and connection metadata. The local launcher does not persist access logs. Production servers/proxies may log IPs, paths and queries: disable query logging or set a short, disclosed retention policy. Avoid publishing user plans or `.cache` contents. Cache records contain public catalog data, not grades or credentials, but filenames/keys can reveal which courses were requested.

## Before a public deployment

Use an HTTPS reverse proxy and the production WSGI server, not `start.py`. Set an exact `PREREQ_HOSTS` allowlist. Trust forwarded protocol headers only from the real proxy; do not trust arbitrary client `X-Forwarded-*` values. The in-process rate limit uses REMOTE_ADDR, so users behind a proxy can share a limit unless the trusted server topology supplies the real address safely. Add per-client limits and request-size/time limits at the edge.

Keep one Gunicorn worker process for this version, because the upstream pacing lock and refresh queue are process-local. Eight worker threads serve cached requests while the separate small refresh pool handles catalog work. Scaling to multiple processes/replicas requires shared scheduling, distributed rate limits and a reviewed cache coordination design.

Use a persistent writable cache volume; keep the application code read-only. Update Python, the pinned production dependency, the base image and development dependencies after testing. No Docker image, penetration test, external security audit or cloud deployment was executed in the build environment. Pin a reviewed image digest for a production release.

## Reporting a problem

For parser failures, report the public source URL, selected major/admission term and observed error. Do not include credentials, a transcript, private student information or an unredacted plan. Handle exploitable vulnerabilities privately with the repository maintainer before public disclosure. No response-time or security warranty is made.


## Hosted configuration added in 2.1

`RENDER_EXTERNAL_HOSTNAME` allows one validated `.onrender.com` hostname, not all Render tenants. Other public hostnames remain explicit entries in `PREREQ_HOSTS`. `PREREQ_PUBLIC_SCHEME=https` pins the expected public Origin for the hosted site even when the immediate WSGI connection is HTTP after TLS termination. Neither `X-Forwarded-Host` nor an arbitrary forwarded protocol can override that check. Public use without a TLS-terminating host is not supported by the Render settings.

Gunicorn binds to PORT, uses one worker/eight threads and limits request/header sizes. Its logs omit query strings, visitor IPs and browser identifiers. The app rate limiter remains keyed by socket peer, so managed proxies can aggregate multiple visitors into a bucket. The supplied configuration prioritizes conservative limits over trusting unverified forwarding headers. Before a large rollout, test concurrency through the chosen host and configure a verified client-IP/rate-limit path. No load test through Render or Cloudflare was performed.

The Free Blueprint uses an ephemeral cache. Production cache durability requires a paid instance and a persistent disk. This release does not automatically provision hosting or authorize paid resources.
