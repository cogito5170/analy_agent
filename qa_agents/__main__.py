"""Command line entry point.

    python -m qa_agents run --spec demo/spec/mini_shop.json --demo-server --out runs/demo
    python -m qa_agents schemas --out schemas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .contracts import REGISTRY
from .orchestrator import Pipeline


def _run(args: argparse.Namespace) -> int:
    spec = json.loads(Path(args.spec).read_text())
    claims = json.loads(Path(args.claims).read_text()) if args.claims else []
    server = None
    base_url = args.base_url
    if args.demo_server:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from demo.target_app import start

        server, base_url = start()
        print(f"demo target app started at {base_url}")
    try:
        board = Pipeline(spec, Path(args.out), base_url=base_url, claims=claims).run(args.phase)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()

    req = board["qa_requirement/1"]
    print(f"requirements : {len(req.requirements)} "
          f"(ambiguities {len(req.ambiguities)}, missing {len(req.missing_requirements)})")
    if (plan := board.get("qa_test_plan/1")) is not None:
        print(f"test cases   : {len(plan.test_cases)}")
    if (obs := board.get("qa_observation/1")) is not None:
        print(f"execution    : {obs.summary}")
    if (dfx := board.get("qa_defect/1")) is not None:
        counts: dict[str, int] = {}
        for t in dfx.triage:
            counts[t.classification] = counts.get(t.classification, 0) + 1
        print(f"triage       : {counts}")
        for d in dfx.defects:
            print(f"  {d.id} [{d.severity}/{d.priority}] {d.title}")
    if (review := board.get("qa_review/1")) is not None:
        print(f"review       : {review.verdict} ({len(review.findings)} findings)")
    if (ev := board.get("qa_evidence/1")) is not None:
        counts = {}
        for c in ev.claims:
            counts[c.strength] = counts.get(c.strength, 0) + 1
        print(f"evidence     : {counts}")
    print(f"output       : {args.out}")
    return 0


def _schemas(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for schema_id, model in REGISTRY.items():
        name = schema_id.replace("/", ".v") + ".schema.json"
        schema = model.model_json_schema(by_alias=True)
        schema["$id"] = schema_id
        (out / name).write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
        print(out / name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qa_agents")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the QA agent pipeline")
    run.add_argument("--spec", required=True, help="feature spec JSON")
    run.add_argument("--out", default="runs/latest", help="run directory")
    run.add_argument("--base-url", help="override the spec's base_url")
    run.add_argument("--demo-server", action="store_true", help="start demo/target_app.py for the run")
    run.add_argument("--claims", help="portfolio claims JSON to verify against evidence")
    run.add_argument("--phase", type=int, choices=(1, 2, 3), default=3,
                     help="1 = core five agents, 2 = + reviewer/evidence, 3 = + portfolio")
    run.set_defaults(func=_run)

    schemas = sub.add_parser("schemas", help="export JSON Schemas for every contract")
    schemas.add_argument("--out", default="schemas")
    schemas.set_defaults(func=_schemas)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
