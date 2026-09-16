# Architecture

```
Browser: forward prerequisite forest + optional list + course panel
  | same-origin catalog API / explicit refresh POST
Python WSGI application
  | validated major / admission term / course code
CatalogService ---- SQLite last-known-good snapshots
  | degree refresh queue + single prerequisite-index worker
OfficialClient ---- fixed-host HTTPS + robots + shared pacing
  |
Public SUIS degree pages -> discovered course pools
Public SUIS course pages -> prerequisite AST + separate corequisite AST
```

## Graph and motion

`web/model.js` is independent of the DOM. It derives a reverse adjacency index from wholly recognized prerequisite expressions: a prerequisite course points to each dependent course. Corequisites are not mixed into that index. Unknown expressions, including an unknown part of an AND, create no partially inferred relationship.

The main forest begins with University and Major required roots. Elective pools follow. Course nodes expand into dependants, not subject folders. Node IDs encode occurrence paths, so the same course can appear in multiple branches without DOM key collisions. Marks are keyed by course code, not occurrence. A source code absent from the degree pool can still appear in the upstream detail view but does not become an invented degree requirement.

Branches are built lazily, with ancestry-cycle checks, a depth guard of 12 and a 1,400-node forward-view limit. True reviewed HUM and MATH choice groups stay explicit. Unparsed choice prose remains available in the official rules rather than being guessed.

`web/app.js` reconciles keyed SVG nodes and edges. Existing positions, entering positions, exit positions and opacity are interpolated for 320 ms with a cubic easing function. New DOM nodes begin invisible at their originating branch, avoiding a one-frame flash. Exiting nodes remain briefly before removal. Repeated toggles cancel and retarget the in-flight animation from its current position.

The camera transform is separate from graph layout. Expansion/collapse only calls `render(false)`, never Fit, Home or Zoom. The clicked node's world position stays fixed while subsequent rows move. Explicit navigation can animate the camera for 300 ms. Resize preserves the center world coordinate. All transitions respect reduced motion. Search/status dimming applies below the animated node, so it does not override the transition opacity.

`ALL`, `OR` and mixed `ALL/OR` labels summarize incoming requirements, with the full AST and minimum grades in the course panel. The optional upstream view includes explicit ALL OF / ANY OF nodes. No view proves registration eligibility.

## Parsing and indexing

`prereq/catalog.py` reads legacy HTML with the standard-library parser. It validates program/admission identity and summary fields, locates section labels and discovers pool URLs. It retains split-core minima and additional program requirements. It accepts singular and plural credit headings, treats empty fields as unknown, and flags recognizable prose-only cohort/program restrictions instead of silently treating an explicit blank field as the complete rule.

`prereq/service.py` stores degree snapshots by major and first admission term. Course details use a separate current-catalog clock. TTL is 12 hours, checked on use. A successful fetch updates its observation time; an error does not. A matching cached or bundled snapshot can be served while checking. There is no cross-major/cohort fallback.

`GET /api/index?program=...&term=...` returns cached details and actual index-job status. The single index worker prioritizes University, Required, Core, Area and Free, with a maximum of 1,500 target codes per job. Each run stops after three consecutive failures or a 20-minute time budget. Subsequent requests can resume stale/unread work after the cooldown. Queue saturation and errors remain visible through coverage information.

Index reads and on-demand/degree reads share the same fixed-origin client and process-local network pacing. Two on-demand refresh threads have a 12-job active/queued limit and per-key single-flight controls. SQLite writes use short-lived connections and transactions. Cache retention is 96 degree snapshots and 3,000 course-detail records. A public deployment must use one worker process unless scheduling and limits are redesigned for shared coordination.

## Offline build and boundaries

`preview.html` and `docs/index.html` embed the same assets and seed, activate explicit offline mode and make no university fetches. Source TSVs and the reviewed factual supplement rebuild the dated seed deterministically.

No student login, transcript ingestion, registration actions, seat monitoring, historical prerequisite reconstruction or automatic graduation audit is included. Current official pages may change or become unavailable. The 12-major registry is configured explicitly and requires review when programs change. Direct live operation was not verified in the build environment; see TESTING.md and SOURCES.md.


## 2.1 startup and deployment

The initial expansion set is empty. Major selection and course markers can be restored, but branch state is deliberately not persisted. User-triggered search still opens a focused course, and explicit navigation/fit/reset can move the camera. Incremental source updates do not reset the user's current expansions.

`render.yaml` provisions one native Python web service when the owner explicitly approves deployment. `gunicorn.conf.py` reads PORT and keeps the process-local shared upstream pacing intact with one worker. The health endpoint reports the package version. Exact Render hostname handling and an explicit public HTTPS scheme avoid manual host guessing and reverse-proxy Origin mismatches. The default test cache is ephemeral; see PUBLISHING.md for persistent disk configuration.
