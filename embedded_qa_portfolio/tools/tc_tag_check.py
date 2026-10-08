"""Test-case tag checker: enforces docs/D2_Test_Case_Guideline.md section 1.  [A03, A10]

Errors
  T01  test function without an @verifies tag in the comment right above it
  T02  @verifies names a requirement that does not exist
  T03  test function defined but never passed to RUN_TEST (it would silently not run)

Also reports which requirements already have at least one unit test.

    python tools/tc_tag_check.py [--json]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FUNC_RE = re.compile(r"^\s*(?:static\s+)?void\s+(test_\w+)\s*\(\s*void\s*\)", re.M)
RUN_RE = re.compile(r"RUN_TEST\(\s*(test_\w+)\s*\)")
TAG_RE = re.compile(r"@verifies\s+((?:SWR-\d{3}\s*,?\s*)+)")


@dataclass
class TestFunc:
    file: str
    name: str
    line: int
    verifies: list[str]


def comment_above(text: str, pos: int) -> str:
    """The /* ... */ comment that ends on the line directly above position pos, if any."""
    before = text[:pos].rstrip()
    if not before.endswith("*/"):
        return ""
    start = before.rfind("/*")
    return before[start:] if start != -1 else ""


def scan(test_dir: Path) -> tuple[list[TestFunc], list[str]]:
    funcs: list[TestFunc] = []
    errors: list[str] = []
    for path in sorted(test_dir.glob("*.c")):
        text = path.read_text()
        registered = set(RUN_RE.findall(text))
        rel = path.relative_to(ROOT)
        for m in FUNC_RE.finditer(text):
            name, line = m.group(1), text.count("\n", 0, m.start()) + 1
            tag = TAG_RE.search(comment_above(text, m.start()))
            ids = re.findall(r"SWR-\d{3}", tag.group(1)) if tag else []
            funcs.append(TestFunc(str(rel), name, line, ids))
            if not ids:
                errors.append(f"T01 {rel}:{line} {name}: no @verifies tag")
            if name not in registered:
                errors.append(f"T03 {rel}:{line} {name}: never passed to RUN_TEST")
    return funcs, errors


def main(argv: list[str]) -> int:
    known = {r["id"] for r in yaml.safe_load((ROOT / "requirements/swr.yaml").read_text())["requirements"]}
    funcs, errors = scan(ROOT / "firmware/test")
    for f in funcs:
        for rid in f.verifies:
            if rid not in known:
                errors.append(f"T02 {f.file}:{f.line} {f.name}: unknown requirement {rid}")

    covered = sorted({rid for f in funcs for rid in f.verifies if rid in known})
    if "--json" in argv:
        print(json.dumps({"tests": len(funcs), "requirements_with_unit_tests": covered,
                          "errors": errors}, indent=2))
    else:
        print(f"{len(funcs)} unit test functions; requirements with unit tests: "
              f"{len(covered)}/{len(known)} {covered}")
        for e in errors:
            print("ERROR", e)
        print(f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
