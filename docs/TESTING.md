# Verification reports

For 2.2.1 use [TESTING-2.2.1.md](TESTING-2.2.1.md).

The report below describes the earlier 2.2.0 build, not the current test run.

---

# PREREQ 2.2 local repair: verification report

## Result

| Check | Result | Scope |
|---|---:|---|
| Python regression, parser, service and transport tests | 160 passed | Real saved BIO degree HTML plus explicitly synthetic Banner fixtures and mocked transport |
| JavaScript model tests | 30 passed | Actual graph model, missing-data behavior, local-plan validation and metadata priority |
| Chromium interface checks | 48 passed | Actual HTML/CSS/JS; all sections closed; camera coordinates and animated frames measured; mobile and reduced-motion checks |
| Chromium-to-application integration checks | 16 passed | Browser test binding to actual WSGI app/service/parsers; synthetic university responses; simulated persisted browser storage |
| Loopback HTTP checks | 11 passed | Actual local HTTP socket and WSGI app; offline source service; Host/Origin/CSP checks |
| Direct live university source check | NOT PASSED | DNS lookup failed before a catalog response was received |

These are not 265 live university tests. The Python suite and browser harness deliberately distinguish the supplied real degree HTML from synthetic catalog/schedule examples. Counts describe local checks only. The integration harness does not prove the real Banner HTML matches every tested template.

## Specific repairs tested

The exact captured Fall 2026 POST encodes to 1,267 bytes with 94 ordered fields and 74 subjects. Repeated subject/dummy fields and blank filters are preserved. Term controls named `cat_term_in`, `term_in` or `p_term` are read from the actual form. Runtime subjects are discovered from the selected term, not blindly reused from the capture.

The transport passes a 45-second timeout, accepts a 4.1 MB test response, rejects over-16-MB responses, closes connections, bounds cookies, validates redirects, and stops on actual 401/403/429/503 and recognized sign-in/challenge pages. Public-query mode and optional robots-exclusion mode have separate tests.

Degree parsing recognizes the exact two-question-mark wrapper links from the supplied BIO HTML. Its 11 required courses and embedded University choices are parsed; unavailable elective pools stay unknown. Synthetic fixtures exercise each of the 12 program identifiers and preserve the selected major/admission identity. This does not establish 12 successfully retrieved live datasets.

Course-rule records are keyed by catalog term and course; schedule records by teaching term and course. Unversioned records are not silently substituted into a selected catalog term. Wrong course/term responses and unknown requirement syntax fail closed. Catalog presence is not used as evidence of offering status.

The interface preserves its monochrome design, subject-colored dots, collapsed startup and 320 ms transitions. Browser checks sample camera coordinates across expansion/collapse and background data updates. Actual current-catalog metadata takes precedence over a degree-pool display title. Partial data does not silently erase local markers.

## Live attempt

`docs/live-source-check.json` contains the actual result:

```text
DNS lookup failed for suis.sabanciuniv.edu. No catalog response was received.
```

The checker stopped after the network failure rather than retrying every source. Degree, prerequisite-detail and schedule checks were marked skipped, not passed. Changing a timeout cannot repair this environment's failed DNS resolution. The live result is not disguised by unit-test success.

## Browser-environment restriction

The installed Chromium blocks direct navigation to loopback URLs. The test harness does not modify or work around that administrative policy. It renders the app in an isolated test page and explicitly calls the local WSGI application through a test binding. A separate Python HTTP smoke test exercises loopback sockets. Browser localStorage persistence is simulated; no claim of real disk-persistence testing is made.

## What was not verified

No production Gunicorn launch, Render deployment, Cloudflare deployment, current live dataset for all majors, fully parsed real Banner POST result, university-approved unattended crawling arrangement, or independent security audit has been completed by these local checks. No GitHub or other account was accessed or modified during this repair.

## Reproduce

```sh
python3 -m unittest discover -s tests -v
node --test tests/model.test.cjs
python3 scripts/http_smoke.py
python3 scripts/browser_smoke.py --chromium /path/to/chromium
python3 scripts/integration_smoke.py --chromium /path/to/chromium
```

The optional read-only source checker uses the production adapters and a temporary cache:

```sh
python3 scripts/check_live.py --program BSBIO --term 202401 --catalog-term 202601 --course "BIO 303"
```

It neither deploys nor changes an account. A nonzero exit and `allVerified: false` must not be presented as success.
