# Changelog

## 2.0.0 · 17 September 2026

- Replaced the classification-tree homepage with a forward prerequisite forest.
- University courses appear first, Major required courses follow, and elective pools stay below.
- Removed marketing copy, subject folders and arbitrary course-number ranges.
- Black background, white text and grayscale controls; color is limited to subject dots.
- Added keyed 320 ms branch expansion/collapse. Camera coordinates and zoom stay unchanged during expansion, collapse, rapid toggles and background index updates.
- Added reduced-motion support, stable clicked-node positioning and explicit-only section navigation.
- Search now opens a course's outgoing prerequisite map; the full upstream AND/OR view remains available in details.
- Expanded the factual seed from 9 to 57 course-detail records. 56 have known prerequisite expressions; contextual or missing rules remain unknown.
- Added a bounded, shared backend prerequisite index with progress, caching, prioritization and outage stop conditions.
- Added regressions for animation, viewport stability, monochrome design, index behavior and contextual prerequisite parsing.

## 1.0.0 · 17 September 2026

Initial classification-tree build, dated EE / Fall 2024 snapshot, nine prerequisite details, local server, plan storage, source adapters and offline preview. Live source retrieval and GitHub publication were not verified/completed in the build environment.
