"""Requirement quality checker for requirements/*.yaml.  [A03, A19, A11]

Errors fail the check (exit code 1); warnings are reported but do not fail.

Errors
  E01  malformed or duplicate id
  E02  missing or unknown parent
  E03  invalid method or priority
  E04  vague wording
  E05  a requirement verified by test has no numeric criterion
  E06  no mandatory wording ("~야 한다" / "안 된다")
  E07  safety goal without a valid ASIL or safe state
  E08  safety goal or feature that no SW requirement refines

Warnings
  W01  more than one mandatory clause: possibly a compound requirement

    python tools/req_check.py [requirements_dir] [--json]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

ID_RE = {
    "safety_goals": re.compile(r"^SG-\d{2}$"),
    "features": re.compile(r"^FN-\d{2}$"),
    "requirements": re.compile(r"^SWR-\d{3}$"),
}
METHODS = {"test", "review", "analysis"}
PRIORITIES = {"must", "should", "could"}
ASILS = {"QM", "A", "B", "C", "D"}
VAGUE = ["빠르게", "신속", "적절", "충분히", "가능한 한", "대부분", "등의", "원활", "최적",
         "효율적", "직관적", "user-friendly", "fast", "appropriate", "as soon as possible"]
NUMBER_RE = re.compile(r"\d")
# Korean mandatory endings: 해야 한다, 이하여야 한다, 보내야 한다, ... and the prohibition 안 된다.
MANDATORY_RE = re.compile(r"야 한다|안 된다")
CLAUSE_RE = re.compile(r"야 (?:한다|하며|하고)")


@dataclass
class Issue:
    code: str
    target: str
    message: str


def load(directory: Path) -> dict[str, list[dict]]:
    merged: dict[str, list[dict]] = {k: [] for k in ID_RE}
    for path in sorted(directory.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key in ID_RE:
            merged[key] += doc.get(key, [])
    return merged


def check(data: dict[str, list[dict]]) -> tuple[list[Issue], list[Issue]]:
    errors: list[Issue] = []
    warnings: list[Issue] = []
    seen: set[str] = set()

    for kind, pattern in ID_RE.items():
        for item in data[kind]:
            rid = str(item.get("id", ""))
            if not pattern.match(rid):
                errors.append(Issue("E01", rid or "?", f"id does not match {pattern.pattern}"))
            if rid in seen:
                errors.append(Issue("E01", rid, "duplicate id"))
            seen.add(rid)

    parents = {i["id"] for i in data["safety_goals"] + data["features"]}
    refined: set[str] = set()
    for req in data["requirements"]:
        rid, text = req.get("id", "?"), str(req.get("text", ""))
        parent = req.get("parent") or []
        if not parent:
            errors.append(Issue("E02", rid, "no parent"))
        for p in parent:
            if p not in parents:
                errors.append(Issue("E02", rid, f"unknown parent {p}"))
            refined.add(p)
        if req.get("method") not in METHODS:
            errors.append(Issue("E03", rid, f"method must be one of {sorted(METHODS)}"))
        if req.get("priority") not in PRIORITIES:
            errors.append(Issue("E03", rid, f"priority must be one of {sorted(PRIORITIES)}"))
        for term in VAGUE:
            if term.lower() in text.lower():
                errors.append(Issue("E04", rid, f"vague wording '{term}'"))
        if req.get("method") == "test" and not NUMBER_RE.search(text):
            errors.append(Issue("E05", rid, "verified by test but has no numeric criterion"))
        if not MANDATORY_RE.search(text):
            errors.append(Issue("E06", rid, "no mandatory wording (~야 한다 / 안 된다)"))
        clauses = len(CLAUSE_RE.findall(text))
        if clauses > 1:
            warnings.append(Issue("W01", rid, f"{clauses} mandatory clauses: consider splitting"))

    for sg in data["safety_goals"]:
        if sg.get("asil") not in ASILS:
            errors.append(Issue("E07", sg["id"], f"asil must be one of {sorted(ASILS)}"))
        if not sg.get("safe_state"):
            errors.append(Issue("E07", sg["id"], "no safe state"))
    for item in data["safety_goals"] + data["features"]:
        if item["id"] not in refined:
            errors.append(Issue("E08", item["id"], "not refined by any SW requirement"))
    return errors, warnings


def summary(data: dict[str, list[dict]]) -> dict[str, object]:
    reqs = data["requirements"]
    by = lambda key: {v: sum(r.get(key) == v for r in reqs) for v in sorted({r.get(key) for r in reqs})}
    return {
        "safety_goals": len(data["safety_goals"]),
        "features": len(data["features"]),
        "requirements": len(reqs),
        "by_method": by("method"),
        "by_priority": by("priority"),
        "by_area": by("area"),
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    directory = Path(args[0]) if args else Path(__file__).resolve().parent.parent / "requirements"
    data = load(directory)
    errors, warnings = check(data)
    if "--json" in argv:
        print(json.dumps({"summary": summary(data), "errors": [asdict(e) for e in errors],
                          "warnings": [asdict(w) for w in warnings]}, ensure_ascii=False, indent=2))
    else:
        s = summary(data)
        print(f"safety goals {s['safety_goals']}, features {s['features']}, "
              f"SW requirements {s['requirements']} {s['by_method']}")
        for issue in errors:
            print(f"ERROR   {issue.code} {issue.target}: {issue.message}")
        for issue in warnings:
            print(f"WARNING {issue.code} {issue.target}: {issue.message}")
        print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
