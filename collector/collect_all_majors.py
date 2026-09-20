#!/usr/bin/env python3
"""
PREREQ all-major collector for the restored v2.0 branch.

What it does:
- Reads official Sabanci degree-requirement pages by program + admission term.
- Expands University / Required / Core / Area sections.
- Intentionally does NOT expand the university-wide Free Elective pool.
- Reuses a shared course-page cache across majors.
- Parses ordinary prerequisite/corequisite rules into the existing v2.0 AST.
- Writes an audit for rules that still need special handling.
- Checkpoints after every major and every new course.

It does NOT publish, commit, push, or touch Cloudflare/GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prereq.catalog import PROGRAM_MAP, parse_expression  # noqa: E402

BASE = "https://www.sabanciuniv.edu"
DEGREE_BASE = BASE + "/en/prospective-students/degree-detail"
COURSE_BASE = BASE + "/en/aday-ogrenciler/lisans/ders-katalogu/course/"
HEADERS = {"User-Agent": "Mozilla/5.0 PREREQ-development"}
OUT = ROOT / "collector" / "output"
OUT.mkdir(parents=True, exist_ok=True)

SHARED_PATH = OUT / "shared-courses.json"
AUDIT_PATH = OUT / "all-majors-audit.json"
SEED_PATH = ROOT / "web" / "seed.json"
OVERRIDES_PATH = ROOT / "collector" / "overrides.json"

DEFAULT_ADMISSION_TERM = "202401"
DEFAULT_TERM_LABEL = "Fall 2024–2025"


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(unescape(href))

    def handle_data(self, data):
        data = data.strip()
        if data:
            self.parts.append(data)


class RowTitleParser(HTMLParser):
    """Extract course-code/title pairs from Sabanci table rows."""
    def __init__(self):
        super().__init__()
        self.in_tr = False
        self.rows = []
        self.row_links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self.in_tr = True
            self.row_links = []
        elif self.in_tr and tag == "a":
            self.current_href = dict(attrs).get("href", "")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self.current_href is not None:
            text = re.sub(r"\s+", " ", "".join(self.current_text)).strip()
            self.row_links.append((self.current_href, text))
            self.current_href = None
            self.current_text = []
        elif tag == "tr" and self.in_tr:
            self.rows.append(self.row_links)
            self.in_tr = False


def fetch(url: str, retries: int = 2) -> str:
    last = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=45) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last = exc
            if attempt < retries:
                time.sleep(2 + 2 * attempt)
    raise last


def parse_page(html: str):
    p = LinkParser()
    p.feed(html)
    text = re.sub(r"\s+", " ", " ".join(p.parts)).strip()
    return p.links, text


def clean_course_text(text: str) -> str:
    # Sabanci's accessibility/footer text follows the course record.
    for marker in ("Accessibility Tool", "Navigation Adjustment"):
        pos = text.find(marker)
        if pos >= 0:
            text = text[:pos]
    return text.strip()


def course_codes(html: str) -> list[str]:
    pairs = re.findall(
        r"subj_code=([A-Za-z]+).*?crse_numb=([A-Za-z0-9]+)",
        html,
        re.I | re.S,
    )
    return sorted({f"{a.upper()} {b.upper()}" for a, b in pairs})


def titles_from_html(html: str) -> dict[str, str]:
    p = RowTitleParser()
    p.feed(html)
    result: dict[str, str] = {}

    for row in p.rows:
        detected = None
        candidates = []

        for href, text in row:
            m = re.search(
                r"subj_code=([A-Za-z]+).*?crse_numb=([A-Za-z0-9]+)",
                href,
                re.I | re.S,
            )
            if not m:
                continue

            code = f"{m.group(1).upper()} {m.group(2).upper()}"
            if detected is None:
                detected = code
            elif detected != code:
                # Wrapper row with more than one course.
                detected = None
                candidates = []
                break

            cleaned = re.sub(r"\s+", " ", text).strip()
            if cleaned and cleaned.upper() != code:
                candidates.append(cleaned)

        if detected and candidates:
            result[detected] = max(candidates, key=len)

    return result


def main_sections(html: str) -> dict[str, list[str]]:
    anchors = list(re.finditer(
        r'<a\s+name=["\']?([^"\'>\s]+)',
        html,
        re.I,
    ))
    result = {"university": [], "required": []}

    for i, match in enumerate(anchors):
        anchor = match.group(1)
        start = match.start()
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(html)
        fragment = html[start:end]

        if anchor.startswith("UC_"):
            result["university"].extend(course_codes(fragment))
        elif anchor.endswith("_REQ"):
            result["required"].extend(course_codes(fragment))

    for key in result:
        result[key] = sorted(set(result[key]))

    return result


def pool_urls(links: list[str]) -> dict[str, list[str]]:
    out = {"core": [], "area": [], "free": [], "faculty": []}

    for href in links:
        if "SU_DEGREE.p_list_courses" not in href:
            continue

        full = urljoin(DEGREE_BASE, href)
        m = re.search(r"P_AREA=([^&]+)", full, re.I)
        if not m:
            continue

        area = m.group(1).upper()

        if area.endswith("_CEL"):
            out["core"].append(full)
        elif area.endswith("_AEL"):
            out["area"].append(full)
        elif area.endswith("_FEL"):
            out["free"].append(full)
        elif area.startswith("FC_"):
            out["faculty"].append(full)

    for key in out:
        out[key] = sorted(set(out[key]))
    return out


def extract_field(text: str, field: str) -> str | None:
    m = re.search(
        rf"\b{re.escape(field)}\s*:?\s*(.*?)"
        rf"(?=\b(?:Prerequisite|Corequisite|ECTS Credit|General Requirements)\s*:|$)",
        text,
        re.I,
    )
    if not m:
        return None
    value = m.group(1).strip()
    return value or None


def normalize_rule(raw: str | None) -> str:
    if not raw:
        return ""

    text = re.sub(r"\s+", " ", raw).strip()

    # Current public wording -> restored v2.0 grammar.
    pattern = re.compile(
        r"Undergraduate\s+level\s+"
        r"([A-Z]{2,8})\s*(\d{3,5}[A-Z]?)"
        r"(?:\s+Minimum\s+Grade\s+of\s+([A-FS][+-]?))?",
        re.I,
    )

    def repl(match):
        code = f"{match.group(1).upper()} {match.group(2).upper()}"
        grade = match.group(3)
        if grade:
            return f"{code} - Undergraduate - Min Grade {grade.upper()}"
        return code

    text = pattern.sub(repl, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text



def derive_degree_choices(sections):
    choices = []

    hum = [
        c["code"] for c in sections.get("university", {}).get("courses", [])
        if c.get("code", "").startswith("HUM ")
    ]
    if len(hum) > 1:
        choices.append({
            "id": "hum",
            "type": "one-of",
            "codes": hum,
        })

    required_codes = {
        c.get("code") for c in sections.get("required", {}).get("courses", [])
    }
    if {"MATH 201", "MATH 202", "MATH 212"}.issubset(required_codes):
        choices.append({
            "id": "math",
            "type": "either",
            "options": [["MATH 212"], ["MATH 201", "MATH 202"]],
        })

    return choices

def degree_url(program_code: str, admission_term: str) -> str:
    # This is the public website wrapper format that was verified from the browser.
    return (
        DEGREE_BASE
        + "?SU_DEGREE.p_degree_detail?P_TERM=" + admission_term
        + "&P_PROGRAM=" + program_code
        + "&P_SUBMIT=&P_LANG=EN&P_LEVEL=UG"
    )


def course_url(code: str) -> str:
    return COURSE_BASE + code.replace(" ", "-")


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value, compact: bool = False):
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        ),
        encoding="utf-8",
    )


def build_course_record(code: str, html: str) -> dict:
    _, text = parse_page(html)
    text = clean_course_text(text)

    if code.lower() not in text.lower():
        raise ValueError("Returned page does not identify requested course")

    return {
        "status": "ok",
        "code": code,
        "source": course_url(code),
        "prerequisite": extract_field(text, "Prerequisite"),
        "corequisite": extract_field(text, "Corequisite"),
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


def collect_program(program_code: str, admission_term: str, shared: dict, seed: dict, audit: dict, overrides: dict, delay: float):
    program = PROGRAM_MAP[program_code]
    program_name = program["name"]
    durl = degree_url(program_code, admission_term)

    print()
    print("=" * 72)
    print(program_code, "-", program_name)
    print("=" * 72)

    degree_html = fetch(durl)
    links, _ = parse_page(degree_html)
    direct = main_sections(degree_html)
    pools = pool_urls(links)

    sections = {
        "university": direct["university"],
        "required": direct["required"],
        "core": [],
        "area": [],
    }

    source_pages = [degree_html]
    titles = titles_from_html(degree_html)

    for category in ("core", "area"):
        found = set()
        for idx, url in enumerate(pools[category], 1):
            print(f"{category} pool {idx}/{len(pools[category])}")
            try:
                html = fetch(url)
                source_pages.append(html)
                found.update(course_codes(html))
                titles.update(titles_from_html(html))
            except Exception as exc:
                audit["errors"].append({
                    "program": program_code,
                    "stage": category,
                    "url": url,
                    "error": str(exc),
                })
            time.sleep(delay)
        sections[category] = sorted(found)

    all_courses = sorted({
        code
        for values in sections.values()
        for code in values
    })

    degree_key = f"{program_code}:{admission_term}"
    global_overrides = overrides.get("global", {})
    degree_overrides = overrides.get("degrees", {}).get(degree_key, {})

    print("University:", len(sections["university"]))
    print("Required:  ", len(sections["required"]))
    print("Core:      ", len(sections["core"]))
    print("Area:      ", len(sections["area"]))
    print("Unique:    ", len(all_courses))

    # Shared fetch cache: same course page is read once and reused by every major.
    for i, code in enumerate(all_courses, 1):
        # A verified global fallback is authoritative for our generated dataset.
        # Do not hammer a known-broken endpoint on every major run.
        if code in global_overrides:
            continue

        existing = shared["courses"].get(code)
        if existing and existing.get("status") == "ok":
            continue

        print(f"  [{i}/{len(all_courses)}] {code} ... ", end="", flush=True)
        try:
            shared["courses"][code] = build_course_record(code, fetch(course_url(code)))
            print("OK")
        except Exception as exc:
            shared["courses"][code] = {
                "status": "error",
                "code": code,
                "source": course_url(code),
                "error": str(exc),
                "checkedAt": datetime.now(timezone.utc).isoformat(),
            }
            audit["errors"].append({
                "program": program_code,
                "course": code,
                "stage": "course",
                "error": str(exc),
            })
            print("ERROR:", exc)

        save_json(SHARED_PATH, shared)
        time.sleep(delay)

    labels = {
        "university": "University Courses",
        "required": "Major required",
        "core": "Core Electives",
        "area": "Area Electives",
    }

    degree_sections = []
    for sid in ("university", "required", "core", "area"):
        degree_sections.append({
            "id": sid,
            "label": labels[sid],
            "rule": "",
            "courses": [
                {
                    "code": code,
                    "title": titles.get(code, code),
                    "ects": None,
                    "credits": None,
                    "faculty": None,
                    "facultyCourse": None,
                    "source": course_url(code),
                    "poolSource": durl,
                }
                for code in sections[sid]
            ],
            "source": durl,
        })

    # Keep Free visible, but do not dump the university-wide pool into the graph.
    degree_sections.append({
        "id": "free",
        "label": "Free Electives",
        "rule": "See the official degree requirements for Free Elective eligibility.",
        "courses": [],
        "source": durl,
    })

    term_label = DEFAULT_TERM_LABEL if admission_term == "202401" else admission_term

    seed["degrees"][f"{program_code}:{admission_term}"] = {
        "schemaVersion": 1,
        "program": program,
        "term": admission_term,
        "termLabel": term_label,
        "source": durl,
        "summary": [],
        "total": {},
        "sections": degree_sections,
        "choices": derive_degree_choices({
            section["id"]: section for section in degree_sections
        }),
        "notes": [],
        "observedAt": datetime.now(timezone.utc).date().isoformat(),
        "origin": "bundled",
        "warnings": [],
        "detailOverrides": {},
    }

    # Global verified fallbacks replace broken/unparseable public course responses.
    for code, override in global_overrides.items():
        if code in all_courses:
            previous = seed["details"].get(code, {})
            seed["details"][code] = {
                **previous,
                **override,
                "code": code,
                "origin": "verified-override",
            }

    # Program/cohort-specific rules belong to the degree, not the shared course record.
    for code, override in degree_overrides.items():
        if code in all_courses:
            seed["degrees"][degree_key]["detailOverrides"][code] = {
                **seed["details"].get(code, {}),
                **override,
                "code": code,
                "origin": "verified-degree-override",
            }

    parsed = 0
    no_prereq = 0
    unknown = 0

    for code in all_courses:
        # Explicit verified overrides take precedence over generic page parsing,
        # even when the normal public endpoint itself is broken.
        if code in global_overrides:
            override_ast = global_overrides[code].get("prerequisite", {"type": "none", "raw": ""})
            if override_ast.get("type") == "none":
                no_prereq += 1
            else:
                parsed += 1
            continue

        if code in degree_overrides:
            override_ast = degree_overrides[code].get("prerequisite", {"type": "none", "raw": ""})
            if override_ast.get("type") == "none":
                no_prereq += 1
            else:
                parsed += 1
            continue

        item = shared["courses"].get(code)
        if not item or item.get("status") != "ok":
            continue

        raw_prereq = item.get("prerequisite") or ""
        raw_coreq = item.get("corequisite") or ""
        norm_prereq = normalize_rule(raw_prereq)
        norm_coreq = normalize_rule(raw_coreq)

        prereq_ast = (
            parse_expression(norm_prereq)
            if norm_prereq else
            {"type": "none", "raw": ""}
        )
        coreq_ast = (
            parse_expression(norm_coreq)
            if norm_coreq else
            {"type": "none", "raw": ""}
        )

        if prereq_ast.get("type") == "unknown":
            unknown += 1
            audit["unknownRules"].append({
                "program": program_code,
                "course": code,
                "raw": raw_prereq,
                "normalized": norm_prereq,
            })
        elif prereq_ast.get("type") == "none":
            no_prereq += 1
        else:
            parsed += 1

        # Ordinary course prerequisites come from the current public course catalog.
        # The restored v2.0 EE seed is historical bundled data, so a successfully
        # parsed current rule replaces it. Program/cohort-specific exceptions were
        # already diverted to degreeOverrides above.
        old = seed["details"].get(code, {})

        if prereq_ast.get("type") != "unknown":
            if old and old.get("prerequisiteText", "") != raw_prereq:
                audit["legacyChanges"].append({
                    "course": code,
                    "old": old.get("prerequisiteText", ""),
                    "current": raw_prereq,
                })

            seed["details"][code] = {
                **old,
                "code": code,
                "title": titles.get(code, old.get("title", code)),
                "source": item["source"],
                "prerequisite": prereq_ast,
                "corequisite": coreq_ast,
                "prerequisiteText": raw_prereq,
                "corequisiteText": raw_coreq,
                "generalRequirements": old.get("generalRequirements", ""),
                "scope": "Current public course catalog; degree membership is admission-term specific.",
                "observedAt": item.get("checkedAt", "")[:10],
                "origin": "bundled-current",
            }
        else:
            # Never replace a known-good rule with an unparsed string.
            if old and old.get("prerequisite", {}).get("type") not in (None, "unknown"):
                audit["ruleConflicts"].append({
                    "program": program_code,
                    "course": code,
                    "existing": old.get("prerequisiteText", ""),
                    "new": raw_prereq,
                    "reason": "Current rule could not be parsed; kept prior known-good value.",
                })

    audit["programs"][program_code] = {
        "name": program_name,
        "university": len(sections["university"]),
        "required": len(sections["required"]),
        "core": len(sections["core"]),
        "area": len(sections["area"]),
        "unique": len(all_courses),
        "parsed": parsed,
        "noPrerequisite": no_prereq,
        "unknown": unknown,
    }

    save_json(SEED_PATH, seed, compact=True)
    save_json(AUDIT_PATH, audit)

    print("Parsed:", parsed)
    print("No prerequisite:", no_prereq)
    print("Unknown:", unknown)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--program",
        action="append",
        help="Collect only this program code. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--term",
        default=DEFAULT_ADMISSION_TERM,
        help="Admission term, e.g. 202401",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between source requests in seconds.",
    )
    args = parser.parse_args()

    if args.program:
        requested = args.program
        unknown_programs = [p for p in requested if p not in PROGRAM_MAP]
        if unknown_programs:
            raise SystemExit("Unknown program(s): " + ", ".join(unknown_programs))
        program_codes = requested
    else:
        program_codes = list(PROGRAM_MAP)

    shared = load_json(SHARED_PATH, {"schemaVersion": 1, "courses": {}})
    seed = load_json(SEED_PATH, {"programs": list(PROGRAM_MAP.values()), "degrees": {}, "details": {}})
    overrides = load_json(OVERRIDES_PATH, {"schemaVersion": 1, "global": {}, "degrees": {}})
    audit = load_json(AUDIT_PATH, {
        "programs": {},
        "unknownRules": [],
        "ruleConflicts": [],
        "legacyChanges": [],
        "errors": [],
    })

    # Rebuild this run's per-program audit cleanly while preserving prior source errors
    # only in the actual cached course records.
    audit["programs"] = {}
    audit["unknownRules"] = []
    audit["ruleConflicts"] = []
    audit["legacyChanges"] = []
    audit["errors"] = []

    for program_code in program_codes:
        try:
            collect_program(
                program_code,
                args.term,
                shared,
                seed,
                audit,
                overrides,
                max(0.5, args.delay),
            )
        except KeyboardInterrupt:
            print("\nStopped by user. Checkpoints are already saved.")
            break
        except Exception as exc:
            print("PROGRAM ERROR:", program_code, exc)
            audit["errors"].append({
                "program": program_code,
                "stage": "program",
                "error": str(exc),
            })
            save_json(AUDIT_PATH, audit)

    print()
    print("=" * 72)
    print("CURRENT AUDIT")
    print("=" * 72)
    for code, row in audit["programs"].items():
        print(
            f"{code:10} "
            f"courses={row['unique']:3} "
            f"parsed={row['parsed']:3} "
            f"none={row['noPrerequisite']:3} "
            f"unknown={row['unknown']:3}"
        )

    print()
    print("Unknown rules:", len(audit["unknownRules"]))
    print("Rule conflicts:", len(audit["ruleConflicts"]))
    print("Legacy rules refreshed:", len(audit["legacyChanges"]))
    print("Errors:", len(audit["errors"]))
    print("Audit:", AUDIT_PATH)


if __name__ == "__main__":
    main()
