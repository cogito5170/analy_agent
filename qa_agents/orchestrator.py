"""Runs the agents in order and enforces the contracts between them.

The orchestrator is the only component that moves documents. After each stage
it re-parses the produced document from JSON (so nothing that only exists as a
Python object can leak between agents), checks that the schema id is the one
the agent promised, and checks that every ID it references exists upstream.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from .agents.base import Agent
from .agents.defect_analyst import DefectAnalyst
from .agents.evidence_analyst import EvidenceAnalyst
from .agents.portfolio_architect import PortfolioArchitect
from .agents.qa_reviewer import QAReviewer
from .agents.requirement_analyst import RequirementAnalyst
from .agents.risk_analyst import RiskAnalyst
from .agents.test_designer import TestDesigner
from .agents.test_executor import TestExecutor
from .contracts import REGISTRY, Contract, ContractError, check_references

FILE_NAMES = {
    "qa_requirement/1": "01_requirement.json",
    "qa_risk/1": "02_risk.json",
    "qa_test_plan/1": "03_test_plan.json",
    "qa_observation/1": "04_observation.json",
    "qa_defect/1": "05_defect.json",
    "qa_review/1": "06_review.json",
    "qa_evidence/1": "07_evidence.json",
    "qa_portfolio/1": "08_portfolio.json",
}
PHASES = {
    1: "qa_defect/1",
    2: "qa_evidence/1",
    3: "qa_portfolio/1",
}


class Pipeline:
    def __init__(self, spec: dict[str, Any], run_dir: Path, base_url: Optional[str] = None,
                 claims: Optional[list[dict]] = None, project_root: Optional[Path] = None):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        executor = TestExecutor(self.run_dir, base_url)
        self.agents: list[Agent] = [
            RequirementAnalyst(spec),
            RiskAnalyst(),
            TestDesigner(),
            executor,
            DefectAnalyst(rerun=executor.rerun),
            QAReviewer(self.run_dir),
            EvidenceAnalyst(self.run_dir, FILE_NAMES, claims or [], project_root or Path.cwd()),
            PortfolioArchitect(FILE_NAMES),
        ]
        self.board: dict[str, Contract] = {}
        self.trace: list[dict[str, Any]] = []

    def run(self, phase: int = 3) -> dict[str, Contract]:
        stop_after = PHASES[phase]
        for agent in self.agents:
            missing = [s for s in agent.consumes if s not in self.board]
            if missing:
                raise ContractError(f"{agent.name} needs {missing} which no earlier stage produced")
            started = time.perf_counter()
            produced = agent.run(self.board)
            doc = produced.to_json()
            if doc.get("schema") != agent.produces:
                raise ContractError(f"{agent.name} promised {agent.produces}, produced {doc.get('schema')}")
            contract = REGISTRY[agent.produces].model_validate(json.loads(json.dumps(doc)))
            self.board[agent.produces] = contract
            problems = check_references(self.board)
            if problems:
                raise ContractError(f"{agent.name}: " + "; ".join(problems))

            path = self.run_dir / FILE_NAMES[agent.produces]
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
            self.trace.append({
                "agent": agent.name,
                "consumes": list(agent.consumes),
                "produces": agent.produces,
                "file": path.name,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            })
            if agent.produces == "qa_portfolio/1":
                (self.run_dir / "portfolio.md").write_text(contract.markdown)
            if agent.produces == stop_after:
                break

        (self.run_dir / "pipeline_trace.json").write_text(
            json.dumps({"phase": phase, "stages": self.trace}, ensure_ascii=False, indent=2))
        return self.board
