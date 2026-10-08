"""Evidence Analyst — asks "is there proof this QA work actually happened?"

Every statement that may end up in a portfolio is a claim, and every claim is
graded by the artifacts behind it:

* strong      — machine-produced execution evidence (run logs, reproduced defects)
* moderate    — a design artifact or code that exists but proves intent, not outcome
* weak        — only prose (README, notes)
* unsupported — no artifact, a missing artifact, or a number nobody measured

Claims come from two places: the pipeline's own results, and an optional list
of claims the user wants to make (``--claims``). User claims that cite numbers
are checked against the metrics this run actually measured.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..contracts import (
    Claim,
    DefectReport,
    EvidenceAnalysis,
    ObservationReport,
    RequirementAnalysis,
    Review,
    RiskAnalysis,
    TestPlan,
)
from .base import Agent, Board

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
EXECUTION_FILES = ("04_observation.json", "05_defect.json")
PROSE_SUFFIXES = (".md", ".txt", ".rst")


def _numbers(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for v in value.values():
            out |= _numbers(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out |= _numbers(v)
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        out.add(f"{value:g}")
        if isinstance(value, float) and 0 <= value <= 1:
            out.add(f"{value * 100:g}")
    return out


class EvidenceAnalyst(Agent):
    name = "Evidence Analyst"
    consumes = ("qa_requirement/1", "qa_risk/1", "qa_test_plan/1", "qa_observation/1",
                "qa_defect/1", "qa_review/1")
    produces = "qa_evidence/1"

    def __init__(self, run_dir: Path, file_names: dict[str, str], user_claims: list[dict],
                 project_root: Path):
        self.run_dir = Path(run_dir)
        self.files = file_names
        self.user_claims = user_claims
        self.root = Path(project_root)

    def run(self, board: Board) -> EvidenceAnalysis:
        req: RequirementAnalysis = board["qa_requirement/1"]
        risk: RiskAnalysis = board["qa_risk/1"]
        plan: TestPlan = board["qa_test_plan/1"]
        obs: ObservationReport = board["qa_observation/1"]
        dfx: DefectReport = board["qa_defect/1"]
        review: Review = board["qa_review/1"]

        m = review.metrics
        executed = m["tests_executed"]
        metrics = {
            **m,
            "pass_rate_pct": round(100 * m["tests_passed"] / executed, 1) if executed else 0,
            "ambiguities": len(req.ambiguities),
            "missing_requirements": len(req.missing_requirements),
            "risk_p0": sum(r.priority == "P0" for r in risk.risks),
            "risk_p1": sum(r.priority == "P1" for r in risk.risks),
            "techniques_used": len(m["techniques"]),
            "execution_seconds": round(sum(o.duration_ms for o in obs.observations) / 1000, 1),
            "review_findings": len(review.findings),
        }

        f = self.files
        claims: list[Claim] = []

        def pipeline_claim(text: str, evidence: list[str], strength: str, note: str = "") -> None:
            exists = all((self.run_dir / e).exists() for e in evidence)
            claims.append(Claim(claim=text, origin="pipeline", evidence=[f"run:{e}" for e in evidence],
                                strength=strength if exists else "unsupported",
                                note=note if exists else "증거 파일 누락"))

        pipeline_claim(
            f"기능 명세를 요구사항 {len(req.requirements)}개로 구조화하고 모호성 "
            f"{len(req.ambiguities)}건, 누락 {len(req.missing_requirements)}건을 식별했다",
            [f["qa_requirement/1"]], "moderate", "설계 산출물")
        pipeline_claim(
            f"리스크 점수(영향도·발생가능성·탐지가능성)로 우선순위를 산정했다 "
            f"(P0 {metrics['risk_p0']}개, P1 {metrics['risk_p1']}개)",
            [f["qa_risk/1"]], "moderate", "설계 산출물")
        pipeline_claim(
            f"테스트 기법 {metrics['techniques_used']}종으로 테스트 케이스 {len(plan.test_cases)}개를 설계했다",
            [f["qa_test_plan/1"]], "moderate", "설계 산출물")
        evidence_logs = sorted({e for o in obs.observations for e in o.evidence})
        pipeline_claim(
            f"자동화 테스트 {executed}개를 실행했다 (통과 {m['tests_passed']}, 실패 {m['tests_failed']})",
            [f["qa_observation/1"], *evidence_logs], "strong", "실행 로그와 요청/응답 기록")
        pipeline_claim(
            f"실패 {len(dfx.triage)}건을 재실행 후 제품 결함/테스트 결함/환경/요구사항 모호성으로 분류했다",
            [f["qa_defect/1"]], "strong" if dfx.triage else "moderate", "재실행 결과 포함")
        for d in dfx.defects:
            pipeline_claim(
                f"{d.id} ({d.severity}) {d.title}",
                d.evidence, "strong" if d.reproducible else "moderate",
                "재실행에서 재현됨" if d.reproducible else "재현되지 않음")
        pipeline_claim(
            f"QA 산출물 자체를 검토해 개선점 {len(review.findings)}건을 도출했다 (판정: {review.verdict})",
            [f["qa_review/1"]], "moderate", "검토 산출물")

        measured = _numbers(metrics)
        for raw in self.user_claims:
            claims.append(self._grade_user_claim(raw, measured))

        return EvidenceAnalysis(claims=claims, measured_metrics=metrics)

    def _grade_user_claim(self, raw: dict, measured: set[str]) -> Claim:
        text, refs = raw["claim"], list(raw.get("evidence", []))
        if not refs:
            return Claim(claim=text, origin="user", evidence=[], strength="unsupported",
                         note="근거 산출물이 제시되지 않음")
        paths = {r: (self.run_dir / r[4:]) if r.startswith("run:") else (self.root / r) for r in refs}
        missing = [r for r, p in paths.items() if not p.exists()]
        if missing:
            return Claim(claim=text, origin="user", evidence=refs, strength="unsupported",
                         note=f"존재하지 않는 산출물: {missing}")
        unmeasured = [n for n in NUMBER_RE.findall(text) if f"{float(n):g}" not in measured]
        if unmeasured:
            return Claim(claim=text, origin="user", evidence=refs, strength="unsupported",
                         note=f"측정되지 않은 수치 {unmeasured} — 실제 측정값으로 바꾸거나 삭제")
        if any(r.startswith("run:") and (r[4:] in EXECUTION_FILES or r[4:].startswith("evidence/"))
               for r in refs):
            strength, note = "strong", "실행 증거로 뒷받침됨"
        elif all(str(p).endswith(PROSE_SUFFIXES) for p in paths.values()):
            strength, note = "weak", "서술 문서만 존재"
        else:
            strength, note = "moderate", "산출물은 있으나 실행 결과로 입증되지 않음"
        return Claim(claim=text, origin="user", evidence=refs, strength=strength, note=note)
