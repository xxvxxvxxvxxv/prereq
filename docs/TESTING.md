# Version 2.1 test report

Observation date: 17 September 2026. Results below describe checks that were actually executed. They do not certify live catalog accuracy, public-load capacity or a deployed hosting account.

| Executed check | Result |
| --- | --- |
| Python unit/integration tests | 70 passed |
| Node pure-model tests | 26 passed |
| Chromium browser assertions | 48 passed |
| Real loopback WSGI HTTP checks | 11 passed |
| JavaScript/Python syntax and shell syntax | Passed |
| Render/Compose YAML parsing | Passed locally, not submitted to Render validation |
| Desktop and 390 × 844 mobile screenshots | Rendered and reviewed |

## Startup behavior regression

The initial map contains exactly five collapsed section nodes and no course nodes or edges. The course detail panel is closed. Opening University does not automatically open course branches or other headings. A startup with a saved major/admission-term selection also starts closed while keeping saved course markers. Returning from the List view through the degree chooser returns to a collapsed Map. Reset closes all branches and the detail panel without deleting the plan.

The saved-startup test uses a simulated localStorage object with values carried into a second initialization. It is a regression test of the application's restoration logic, not a native disk-persistence test.

## Motion regression retained

The browser harness samples the actual SVG viewport and clicked-node transforms over animation frames. Opening and closing course branches preserves camera translation, camera scale and the clicked anchor, including after manual panning and zooming. Opening a section also preserves the camera. Intermediate positions and opacities verify animation rather than an instant swap. Rapid toggles settle without duplicate node IDs. Elective-pool and keyboard collapse paths retain the same invariant. Fit, section navigation and Reset are explicit navigation actions and can move the camera.

A controlled mocked index response adds a previously unknown relationship without changing the viewport. This tests the frontend update path, not the real university connection.

## Hosting regression tests

New Python tests cover exact Render hostname registration; rejection of another Render tenant and malformed injected hostname; explicit custom-domain permission; HTTPS Origin validation through an HTTP WSGI connection; rejection of insecure/foreign Origins and spoofed forwarded headers; unchanged localhost behavior; invalid public-scheme rejection; Gunicorn port/thread/worker limits and non-wildcard forwarded-header configuration; and a Free-only, single-web-service Blueprint.

The portable `scripts/http_smoke.py` starts a real loopback WSGI server in offline mode. Its 11 checks verify the application HTML rather than the standalone preview, versioned health endpoint, collapsed-state application script, API presence, matching seed availability, response headers, hosted HTTPS Origin acceptance, foreign Origin rejection, foreign Host rejection, private cache non-exposure and no-store API responses. It sends explicit Host/Origin values over the loopback connection to exercise the managed-proxy configuration path. It does not start Gunicorn or provide TLS.

## Existing coverage retained

Python tests cover program/cohort identity, course/term validation, pool discovery, atomic refresh, retaining original dates after refresh failure, no cross-major fallback, cache priority, background index single-flight and failure limits. Prerequisite parsing tests cover mixed AND/OR, minimum grades, explicit none versus unknown, contextual unknown conditions, corequisites, split-core sections and additional requirements. Parser fixtures are reconstructed HTML, not archived upstream responses.

Targeted security tests cover approved upstream hosts/paths/parameters, credentials/port restrictions, private DNS addresses, robots denial/failure, required API request header, Host/Origin checks, traversal and duplicate-query rejection, static-file allowlisting and response headers. These are targeted checks, not an independent penetration test. The hosted per-socket-peer rate limiter is deliberately conservative; a reverse proxy may aggregate visitors. Public load testing and a deployment-specific trusted-client-IP configuration remain outstanding.

Model tests cover forward direction, University-first ordering, absence of category prerequisite edges and course-number folders, course choices, stable occurrence IDs, cycle guards, search/status structure, subject dots, incoming ALL/OR logic, absence of corequisite unlock edges, partial coverage and plan validation.

Chromium also exercises search, full prerequisite/corequisite details, source coverage, marking, filters, JSON import/export, wrong-cohort rejection, unknown prerequisites, unavailable-major recovery, mobile layout and pointer behavior, reduced motion and literal rendering of malicious-looking source strings. Exact browser assertion names are in `browser-checks.json`; loopback names are in `http-checks.json`.

## Validation boundaries

The browser harness uses `page.set_content` with the generated standalone HTML and a Map-backed localStorage substitute on about:blank. Direct file navigation is blocked by this environment's browser policy. Real browser disk persistence and production CSP enforcement through a deployed full-page navigation are not claimed.

A direct source check was attempted with `scripts/check_live.py --program BSEE --term 202401`; it failed at DNS resolution with `Temporary failure in name resolution`. This release leaves the bundled EE / Fall 2024 dataset unchanged: 624 course options and 57 detail records. Live fetching/indexing across all 12 configured majors remains unverified. Source dates must not be interpreted as a new successful university fetch caused by this UI release.

Production Gunicorn installation could not be completed because package-host DNS resolution also failed. Its configuration was tested as Python code, but a Gunicorn process and Docker production image were not run. Hosting documentation was checked against official provider docs; the actual Render Blueprint, domain verification, TLS termination and hosted-to-university connection were not exercised. No GitHub repository, cloud service or domain was created by these tests.

Not executed: complete live catalog crawl, public traffic load test, independent security/accessibility audit, physical-device testing, Safari/Firefox, actual macOS/Windows launchers, native disk-persistence test or cloud deployment.

## Reproduce

From the extracted project root:

```sh
python3 -m unittest discover -s tests -v
node --test tests/model.test.cjs
python3 scripts/build_seed.py
python3 scripts/build_preview.py
python3 scripts/http_smoke.py
python3 scripts/browser_smoke.py --chromium /path/to/chromium --screenshots docs
python3 scripts/check_live.py --program BSEE --term 202401
```

Node is needed only for JavaScript tests. The browser command needs the optional Playwright package and a compatible Chromium executable. The final command performs a real source check and should fail visibly when the official server cannot be reached or access is blocked. The other suites use local data or controlled mocks.
