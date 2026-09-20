#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prereq.catalog import PROGRAM_MAP

SEED = ROOT / "web" / "seed.json"
AUDIT = ROOT / "collector" / "output" / "all-majors-audit.json"

TERMS = ("202301", "202401", "202501", "202601")

seed = json.loads(SEED.read_text(encoding="utf-8"))
audit = json.loads(AUDIT.read_text(encoding="utf-8"))

errors = []

programs = list(PROGRAM_MAP)
if len(programs) != 12:
    errors.append(f"Expected 12 programs, found {len(programs)}")

missing = []
for program in programs:
    for term in TERMS:
        key = f"{program}:{term}"
        if key not in seed.get("degrees", {}):
            missing.append(key)
            continue

        degree = seed["degrees"][key]
        section_ids = {s.get("id") for s in degree.get("sections", [])}
        expected = {"university", "required", "core", "area", "free"}
        if not expected.issubset(section_ids):
            errors.append(
                f"{key}: missing sections {sorted(expected - section_ids)}"
            )

if missing:
    errors.append("Missing degree snapshots: " + ", ".join(missing))

unknown = audit.get("unknownRules", [])
conflicts = audit.get("ruleConflicts", [])
source_errors = audit.get("errors", [])

if conflicts:
    errors.append(f"Rule conflicts remain: {len(conflicts)}")

if source_errors:
    errors.append(f"Source errors remain: {len(source_errors)}")

unexpected_unknown = [
    x for x in unknown
    if not (x.get("program") == "BSDSA" and x.get("course") == "DSA 492")
]
if unexpected_unknown:
    errors.append(
        f"Unexpected unresolved rules: {len(unexpected_unknown)}"
    )

if not (ROOT / "docs" / "favicon.ico").exists():
    errors.append("docs/favicon.ico is missing")

app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
model = (ROOT / "web" / "model.js").read_text(encoding="utf-8")

for needle, label in [
    ("admissionLabel", "simplified admission-term UI"),
    ("detailOverrides", "degree-specific rule overrides"),
    ("subject-legend", "dynamic subject legend"),
]:
    if needle not in app:
        errors.append(f"app.js missing {label}")

for needle, label in [
    ("ALL ${", "ALL N logic badges"),
    ("ANY ${", "ANY N logic badges"),
    ("RULE", "mixed-rule badge"),
]:
    if needle not in model:
        errors.append(f"model.js missing {label}")

print("PREREQ RELEASE CHECK")
print("====================")
print("Programs:", len(programs))
print("Admission terms:", ", ".join(TERMS))
print("Expected degree snapshots:", len(programs) * len(TERMS))
print("Present degree snapshots:", sum(
    1 for p in programs for t in TERMS if f"{p}:{t}" in seed.get("degrees", {})
))
print("Audit unknown rules:", len(unknown))
print("Audit rule conflicts:", len(conflicts))
print("Audit source errors:", len(source_errors))
print()

if unknown:
    print("Known unresolved:")
    for row in unknown:
        print(" ", row.get("program"), row.get("course"), "->", row.get("raw"))
    print()

if errors:
    print("RELEASE CHECK: FAIL")
    for e in errors:
        print(" -", e)
    raise SystemExit(1)

print("RELEASE CHECK: PASS")
print("Only DSA 492 may remain intentionally unresolved.")
