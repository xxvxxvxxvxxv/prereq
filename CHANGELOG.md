# 2.2.0 local repair

Implemented the actual Banner catalog form flow, including ordered multi-value POSTs, 45-second source timeouts and a 16 MB response cap. The previous 10-second/2 MB GET-only transport could not execute the supplied search.

Separated catalog-term course rules, cohort-specific degree categories and teaching-term Dynamic Schedule observations. No diagram, recommended semester plan or generic degree-page link is promoted to a current prerequisite edge.

Implemented the university's nested-query degree links and generic per-program degree parsing, including majors whose summaries omit a category. Linked pool failures remain incomplete; complete cached snapshots are retained. The saved BIO page supplies a real partial fallback instead of a blank map.

Added a separate Catalog selector, on-demand section checks, scoped cache keys, missing-data labels and preservation of local plan markers across partial refreshes. Kept black/white styling, subject dots, all sections closed on startup, and the stable-camera 320 ms transitions.

Changed the self-imposed robots gate into an explicit operator policy choice. Public-query mode still stops on actual HTTP refusals, sign-in and verification pages. It is not a claim of university permission or robots-compliant crawling.

Corrected the production dependency to gunicorn==26.2.0. Removed automatic publishing helpers/workflows from the local package. No account or deployed project was accessed or modified.

Local tests pass; the direct live check failed at DNS resolution. All-major live data remains unverified. See docs/TESTING.md.
