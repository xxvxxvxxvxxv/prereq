# PREREQ 2.2 architecture

The frontend is vanilla JavaScript/CSS/SVG. The local Python WSGI server uses the standard library. Production compatibility uses Gunicorn; there is no frontend build dependency.

`prereq/network.py` owns bounded HTTPS requests, public form POSTs, anonymous sessions, route/host validation, optional robots exclusion and actual HTTP refusal handling.

`prereq/banner.py` discovers official term/search controls and parses term-specific catalog and schedule HTML. The ordered catalog POST preserves repeated `sel_subj` controls. Unknown prerequisite conditions remain unknown. Section/CRN evidence only comes from schedule results.

`prereq/catalog.py` parses major/cohort requirements and both direct SUIS and two-question-mark university wrapper links. `degree_snapshot.py` parses a saved degree document without inventing linked pools.

`prereq/service.py` stores dated snapshots in SQLite, debounces API refreshes and serializes shared indexing. Cache keys separate `degree:program:admitTerm`, `catalog:catalogTerm`, `course:catalogTerm:code`, and `schedule:teachingTerm:code`. Old unversioned course keys are exposed only in explicit saved-reference mode.

`prereq/app.py` exposes same-origin read APIs and a bodyless POST refresh. It does not expose arbitrary upstream URLs or authentication endpoints. Static files are an explicit list.

`web/model.js` builds outgoing prerequisite relationships from wholly parsed expressions. Corequisites are separate. Unknown conjuncts do not become partially asserted eligibility. `web/app.js` preserves viewport coordinates during keyed SVG transitions and separates the three term selectors. Local plans are never transmitted.

Verification is described in TESTING.md. The adapters are implemented, but source HTML variations and live networking across all majors are not established by fixture tests.
