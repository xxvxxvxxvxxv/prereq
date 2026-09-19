# Version 2 test report

Observation date: 17 September 2026. These results describe executed tests, not a guarantee of live catalog accuracy or every deployment environment.

| Executed check | Result |
| --- | --- |
| Python unit/integration tests | 58 passed |
| Node pure-model tests | 24 passed |
| Chromium browser assertions | 41 passed |
| Loopback HTTP requests | Six tested asset/API routes returned 200 with CSP headers; health also responded |
| JavaScript and Python syntax | Passed |
| Desktop and 390 × 844 mobile screenshots | Rendered and visually reviewed |

## The camera regression

The browser harness sampled the actual viewport transform and clicked course-node transform over animation frames. For both opening and closing a branch, the viewport translation and scale stayed identical. The clicked course's world position also stayed identical. This was repeated after manual panning and zooming.

Entering nodes had intermediate positions and opacities before settling. Exiting nodes remained during the animation and were then removed. A series of rapid toggles settled without duplicate DOM IDs or recentering. An elective pool expanded with the same camera invariant; keyboard collapse did too. Explicit section navigation and Reset moved the camera only when requested.

A controlled mocked index response added a previously unknown course relationship while the viewport stayed fixed. This exercises the production frontend's index-response path, not the real university network.

## Other tested behavior

Python covers strict codes/terms, program/cohort identity, discovered pool links, atomic refresh and unchanged dates on failure, no cross-major fallback, cache priority, index single-flight, stop-after-three-failures behavior, current-detail storage and offline no-network behavior. Parsing covers mixed AND/OR, grades, explicit none versus unknown, singular and zero-credit headings, description-only contextual requirements, split-core sections, additional requirements and HTML limits.

Targeted security tests cover the approved upstream URL/parameter allowlist, credential/port/host restrictions, private DNS addresses, robots failure/denial, required same-origin API header, Host/Origin checks, traversal/duplicate-query rejection, static file exposure and response headers. These are not a penetration test.

Model tests cover forward direction, no category-to-course prerequisite edges, no number-range folders, University-first ordering, real HUM/MATH choices, course-occurrence IDs, cycle guards, status/search structure retention, subject-dot classification, incoming ALL/OR preservation, absence of corequisite unlock edges, partial coverage and plan validation.

Chromium also checks white text/black background, subject dots, initial University/Required visibility, forward search focus, full prerequisite and corequisite details, source coverage, marking, completed filters, JSON export/import, wrong-cohort rejection, unknown requirements, returning from an unavailable major, mobile Map default, touch-pointer panning, mobile detail layout, reduced motion and literal rendering of malicious-looking source strings.

The exact browser assertion names are in `browser-checks.json`.

## Harness limits

The browser uses `page.set_content` with the actual standalone HTML. A Map-backed localStorage substitute is injected for the about:blank origin. Therefore these assertions verify UI behavior and storage logic, not native browser disk persistence.

A local offline Python server was started, and real loopback requests checked `/`, `/app.js`, `/model.js`, `/styles.css`, `/api/index?program=BSEE&term=202401`, `/api/course?code=EE%20202` and `/health`. Chromium navigation to that loopback URL was attempted but blocked by the environment with `ERR_BLOCKED_BY_ADMINISTRATOR`. Production CSP enforcement through full browser navigation is not claimed.

Direct university fetching failed at DNS resolution in this environment. The research browser could read the official pages used for the factual snapshot. Parser fixtures are explicitly reconstructed HTML, not archived upstream responses. End-to-end live indexing for the 12 configured majors remains unverified.

Not executed: full live catalog crawl, cloud/GitHub deployment, Docker production build, physical-device testing, Safari/Firefox, macOS/Windows launcher execution, external security/accessibility audit or public traffic load testing.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
node --test tests/model.test.cjs
python3 scripts/build_seed.py
python3 scripts/build_preview.py
python3 scripts/browser_smoke.py --chromium /path/to/chromium --screenshots docs
python3 scripts/check_live.py --program BSEE --term 202401
```

The browser command needs the optional Playwright package. The final command is a real source check and should fail visibly if the official server is unavailable or access is blocked.
