![PREREQ — Course pathways](docs/prereq-banner.png)

# PREREQ — course pathways

Choose a major, expand its courses, and see their prerequisite relationships. Static Cloudflare app; no visitor-triggered scraping, degree totals or admission-year requirement pages.

For this complete project, read [UPLOAD.md](UPLOAD.md) or START-HERE.txt. No previous folder is required. The included reference data is incomplete; run the collector to populate current course rules.

```sh
python scripts/update_snapshots.py
npm run deploy
```

The collector reads the pinned course catalog and course details. Progress is printed and data/update-report.json lists unresolved rules by major. Public source responses for failed parses are saved in data/source-failures. Unknown prerequisites remain unknown.

All 12 programs use subject mappings in data/update-config.json. The graph includes subject courses with undergraduate numbers and linked ENS foundations; other prerequisites remain accessible in course details. This is not a graduation requirement checker.

UPLOAD.md includes Cloudflare publishing and optional daily GitHub updates. Historical reports describe previous releases.

MIT license. Independent student tool.
