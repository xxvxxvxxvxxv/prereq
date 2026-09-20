#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
seed = json.loads((ROOT / "web" / "seed.json").read_text(encoding="utf-8"))

TERMS = ("202301", "202401", "202501", "202601")
programs = seed.get("programs", [])
degrees = seed.get("degrees", {})
details = seed.get("details", {})

errors = []

if len(programs) != 12:
    errors.append(f"expected 12 programs, found {len(programs)}")

for program in programs:
    pid = program["id"]
    for term in TERMS:
        key = f"{pid}:{term}"
        degree = degrees.get(key)
        if not degree:
            errors.append(f"missing degree snapshot {key}")
            continue

        section_ids = {s.get("id") for s in degree.get("sections", [])}
        expected = {"university", "required", "core", "area", "free"}
        missing = expected - section_ids
        if missing:
            errors.append(f"{key}: missing sections {sorted(missing)}")

        effective = {**details, **degree.get("detailOverrides", {})}
        for section in degree.get("sections", []):
            for course in section.get("courses", []):
                code = course.get("code")
                detail = effective.get(code)
                if not detail:
                    errors.append(f"{key}: missing detail for {code}")
                    continue
                ptype = (detail.get("prerequisite") or {}).get("type")
                if ptype == "unknown" and not (pid == "BSDSA" and code == "DSA 492"):
                    errors.append(f"{key}: unexpected unresolved prerequisite {code}")

if errors:
    print("CI RELEASE CHECK: FAIL")
    for error in errors[:100]:
        print(" -", error)
    raise SystemExit(1)

print("CI RELEASE CHECK: PASS")
print(f"{len(programs)} programs × {len(TERMS)} admission terms = {len(programs)*len(TERMS)} snapshots")
print("DSA 492 is the only permitted unresolved prerequisite.")
