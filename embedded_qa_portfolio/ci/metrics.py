"""Collect pipeline results into metrics.json and summary.md.

Reads the files ci/pipeline.sh leaves in its output directory. Missing files
mean the step did not run; the metric is then null, never a guessed value.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def read(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def main(out: Path) -> None:
    steps = {}
    for line in (read(out / "steps.tsv") or "").splitlines():
        name, status, seconds = line.split("\t")
        steps[name] = {"status": status, "seconds": float(seconds)}

    tests = None
    if (log := read(out / "unit_test.log")) and (m := re.search(r"(\d+) tests? failed out of (\d+)", log)):
        tests = {"total": int(m.group(2)), "failed": int(m.group(1))}
    unity = None
    if (out / "host" / "Testing").exists() and log:
        cases = re.findall(r"(\d+) Tests (\d+) Failures (\d+) Ignored", log)
        if cases:
            unity = {"cases": sum(int(c[0]) for c in cases), "failures": sum(int(c[1]) for c in cases)}

    coverage = None
    if gcov := read(out / "gcov.txt"):
        def pct(label: str) -> float | None:
            m = re.search(label + r":([\d.]+)% of \d+", gcov)
            return float(m.group(1)) if m else None
        coverage = {"line_pct": pct("Lines executed"), "branch_taken_pct": pct("Taken at least once")}

    arm = None
    if size := read(out / "arm_size.txt"):
        total = size.strip().splitlines()[-1].split()
        arm = {"text": int(total[0]), "data": int(total[1]), "bss": int(total[2])}

    repro = steps.get("reproducible", {}).get("status")
    metrics = {
        "commit": os.environ.get("GITHUB_SHA") or git("rev-parse", "HEAD"),
        "total_seconds": round(sum(s["seconds"] for s in steps.values()), 2),
        "steps": steps,
        "ctest": tests,
        "unity": unity,
        "coverage": coverage,
        "arm_library_bytes": arm,
        "reproducible_debug_build": None if repro in (None, "skipped") else repro == "passed",
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")

    rows = "\n".join(f"| {n} | {s['status']} | {s['seconds']:.2f} |" for n, s in steps.items())
    cov = coverage or {}
    summary = f"""## Firmware pipeline

| step | status | seconds |
|---|---|---|
{rows}

- total: {metrics['total_seconds']} s
- unit test cases: {unity['cases'] if unity else 'n/a'} (failures: {unity['failures'] if unity else 'n/a'})
- coverage (app): line {cov.get('line_pct', 'n/a')}%, branch taken {cov.get('branch_taken_pct', 'n/a')}%
- ARM library size: {f"text {arm['text']} B, data {arm['data']} B, bss {arm['bss']} B" if arm else 'n/a (not built)'}
- reproducible Debug build: {metrics['reproducible_debug_build']}
"""
    (out / "summary.md").write_text(summary)
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a") as f:
            f.write(summary)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
