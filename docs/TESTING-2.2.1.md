# PREREQ 2.2.1: local verification

## What was actually diagnosed

In the shipped 2.2.0 code, both `graph_index` and a term-specific `course` lookup required a successful university-wide semester-catalog fetch. A failure in that fetch prevented even an individual course's detail request. Degree requirements used a separate path and could already be available.

This is a reproduced code defect, not a confirmed exclusive explanation for the user's particular hosted request. The screenshot showed `Degree checked` and `0/624 prerequisites checked` while checking was active. It did not reveal the underlying network or parsing error.

## Same failure, old and new versions

The same synthetic upstream was used in two separate Python processes. It refuses the aggregate-catalog selector but answers an exact-course POST and that course's linked detail page.

| Version | Observed sequence | Result |
|---|---|---|
| 2.2.0 | GET semester catalog selector; simulated failure | Course read fails without attempting its own query |
| 2.2.1 | POST subject/course-filtered catalog search; GET returned course-detail link | Course identity, term, prerequisite logic and separate corequisite are parsed |

Machine-readable traces are in `checks-2.2.1/before.json` and `after.json`. Their course content is explicitly synthetic. It is NOT a newly collected Sabancı dataset and is not used as application seed data.

## Verification run

| Check | Result | Scope |
|---|---:|---|
| Python suite | 184 passed | Includes the original 160 checks plus 24 course-isolation regressions; real saved BIO degree fixture, synthetic Banner responses and mocked transport |
| JavaScript model suite | 30 passed | Actual graph and plan model |
| Chromium UI suite | 48 passed | Actual HTML, CSS, JavaScript, animation/camera sampling, mobile layout; storage simulated |
| Chromium + application integration | 16 passed | Real WSGI application, service and parser via an explicit test binding; synthetic upstream replies |
| Local HTTP suite | 11 passed | Actual loopback WSGI socket, version, assets, API, Host/Origin/security-header checks |
| Direct university source check | NOT PASSED | DNS resolution failed before any university response |

The Python count excludes imported helper test classes, so the helper suite is not counted twice.

The new regressions verify course-specific requests without aggregate data; index startup without an aggregate snapshot; all 12 program identifiers retaining their own synthetic course; cross-major cache sharing; concurrent request coalescing; catalog-term isolation; real observation-date preservation; progress reporting; unknown rules; lab/companion results; strict response identity; minimum grades; AND/OR; and course-heading variants.

The 12-program routing test does not mean that 12 real live major datasets were fetched successfully.

## Actual live attempt

`checks-2.2.1/live-source-check.json` records the direct anonymous course-specific query attempt:

```text
DNS lookup failed for suis.sabanciuniv.edu. No catalog response was received.
```

It failed before HTTP. The remaining source checks were skipped rather than retried after that network failure. Earlier attempts to inspect the public deployment from this runtime also failed at DNS. None of these results prove that Render or Sabancı is unreachable from the user's network.

## Bundled data is not live coverage

The package still contains the original 624 unique EE/Fall-2024 degree course options and 57 unversioned example detail records. BIO's user-supplied Fall-2024 partial degree contains 35 unique course options, including its 11 required courses. There are no fabricated term-specific seed records (`catalogDetails` is empty).

The old EE display was therefore not evidence of a working live prerequisite collector, nor a complete prerequisite dataset. This release fixes request orchestration instead of copying EE data into another major or assigning current-term labels to old records.

## Changed production files

```text
prereq/__init__.py
prereq/app.py
prereq/banner.py
prereq/service.py
web/app.js
```

Unchanged: subject colors; styles and layout; expand/collapse behavior; camera positioning; degree parser and sources; Dynamic Schedule adapter; transport timeout, host allowlist, access-refusal handling and fetch policy; Render configuration; dependencies; and database schema.

The index reads major-required courses first, then University courses and electives. That is a request-priority change only; the on-screen category order is unchanged. Validated term/course records remain shared across majors. Existing aggregate snapshots can speed up lookups but are no longer mandatory. The counter shows the course being read and distinguishes loaded pages from parsed rules and failures.

## Not established by these tests

No successful real Banner exact-course query from the deployment, complete all-major live dataset, production Gunicorn launch, production TLS check, hosted deployment, or university-approved unattended access arrangement was established. Gunicorn is not installed in this build runtime. No GitHub or other account was accessed or changed during this repair. The user's live site remains unchanged until they choose to deploy new files.

## Reproduce locally

```sh
python3 -m unittest discover -s tests -v
node --test tests/model.test.cjs
python3 scripts/http_smoke.py
python3 scripts/browser_smoke.py --chromium /path/to/chromium
python3 scripts/integration_smoke.py --chromium /path/to/chromium
```

The optional `scripts/check_live.py` checks one course first, before any optional whole-catalog query. It performs no account, repository, or deployment operations. A failure remains a failure in its report.
