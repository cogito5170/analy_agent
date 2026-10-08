"""Defect Analyst — triages failures before anything is called a bug.

A failed test is a symptom, not a verdict. Each failure is re-run once and then
classified as one of:

* product_bug           — the system violates a requirement, reproducibly
* test_bug              — the test is wrong (bad data, non-deterministic test)
* environment           — infrastructure, not the product (connection, 502/503/504)
* requirement_ambiguity — the test's oracle rests on an assumption the spec never made
* spec_mismatch         — reasonable behaviour that differs from the spec; ask the PO

Only product bugs become defect reports. Failures with the same root symptom
(same endpoint, same kind of violation) are merged into one report.
"""

from __future__ import annotations

import json
import math
from typing import Callable, Optional

from ..contracts import (
    AssertionResult,
    Defect,
    DefectReport,
    InputField,
    Observation,
    ObservationReport,
    Requirement,
    RequirementAnalysis,
    RiskAnalysis,
    TestCase,
    TestPlan,
    Triage,
)
from .base import Agent, Board

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
TRANSIENT = {502, 503, 504}
# The simplest reproducer of a defect makes the best report, so prefer it.
TECHNIQUE_RANK = {"negative": 0, "happy_path": 0, "equivalence_partitioning": 1, "boundary_value": 1,
                  "decision_table": 2, "security_negative": 2, "state_transition": 3, "performance": 3}


def _first_failure(obs: Observation) -> tuple[Optional[AssertionResult], Optional[int]]:
    for r in obs.step_results:
        for a in r.assertions:
            if not a.passed:
                return a, (r.response or {}).get("status")
    return None, None


def _readable(data: dict) -> str:
    """JSON for a bug report, with long generated values shortened to their length."""
    short = {k: (f"{v[:6]}…({len(v)}자)" if isinstance(v, str) and len(v) > 40 else v)
             for k, v in data.items()}
    return json.dumps(short, ensure_ascii=False)


def _signature(obs: Observation) -> tuple:
    failed, status = _first_failure(obs)
    return (obs.status, failed.type if failed else None, status)


def _violates(data: dict, inputs: list[InputField]) -> Optional[str]:
    """Return why ``data`` breaks the spec's own input rules, if it does."""
    for f in inputs:
        v = data.get(f.name)
        if v is None:
            if f.required:
                return f"필수 입력 '{f.name}' 누락"
            continue
        if isinstance(v, str):
            if f.min_length is not None and len(v) < f.min_length:
                return f"'{f.name}' 길이 {len(v)} < {f.min_length}"
            if f.max_length is not None and len(v) > f.max_length:
                return f"'{f.name}' 길이 {len(v)} > {f.max_length}"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if f.minimum is not None and v < f.minimum:
                return f"'{f.name}' 값 {v} < {f.minimum}"
            if f.maximum is not None and v > f.maximum:
                return f"'{f.name}' 값 {v} > {f.maximum}"
    return None


class DefectAnalyst(Agent):
    name = "Defect Analyst"
    consumes = ("qa_requirement/1", "qa_risk/1", "qa_test_plan/1", "qa_observation/1")
    produces = "qa_defect/1"

    def __init__(self, rerun: Optional[Callable[[TestCase], Observation]] = None):
        self.rerun = rerun

    def run(self, board: Board) -> DefectReport:
        analysis: RequirementAnalysis = board["qa_requirement/1"]
        risk: RiskAnalysis = board["qa_risk/1"]
        plan: TestPlan = board["qa_test_plan/1"]
        report: ObservationReport = board["qa_observation/1"]

        reqs = {r.id: r for r in analysis.requirements}
        priorities = {r.req_id: r.priority for r in risk.risks}
        cases = {t.id: t for t in plan.test_cases}

        triage: list[Triage] = []
        groups: dict[str, dict] = {}
        clarifications: list[dict[str, str]] = []

        for obs in report.observations:
            if obs.status not in ("failed", "error"):
                continue
            tc, req = cases[obs.test_id], reqs[obs.req_id]
            retry = self.rerun(tc) if self.rerun and obs.status == "failed" else None
            reproduced = None if retry is None else _signature(retry) == _signature(obs)
            note, noise, evidence = "", None, list(obs.evidence) + (list(retry.evidence) if retry else [])
            entry_reproduced = reproduced
            _, first_status = _first_failure(obs)
            if retry is not None and retry.status == "failed" and not reproduced and first_status in TRANSIENT:
                # The first failure was transient infrastructure noise; judge the test by what
                # the rerun shows once the noise is gone.
                note = f"첫 실행은 일시적 HTTP {first_status}(환경) — 재실행 결과로 판정. "
                noise = f"HTTP {first_status} on first attempt, not on rerun"
                obs, retry, reproduced = retry, None, False
            cls, reason, signature, kind = self._classify(obs, tc, req, retry)
            entry = Triage(test_id=tc.id, classification=cls, reason=note + reason,
                           reproduced_on_rerun=entry_reproduced, transient_noise=noise)
            triage.append(entry)

            if cls == "requirement_ambiguity":
                clarifications.append({"req_id": req.id, "test_id": tc.id,
                                       "question": f"{tc.assumption} (관찰값: {obs.actual})"})
            if cls == "spec_mismatch":
                clarifications.append({"req_id": req.id, "test_id": tc.id,
                                       "question": f"명세는 '{obs.expected}', 실제는 '{obs.actual}' — "
                                                   "어느 쪽이 의도된 동작인지 확인 필요"})
            if cls != "product_bug":
                continue
            g = groups.setdefault(signature, {"kind": kind, "tests": [], "evidence": [],
                                              "entries": [], "reproduced": True})
            g["tests"].append((tc, obs, req))
            g["evidence"] += evidence
            g["entries"].append(entry)
            g["reproduced"] = g["reproduced"] and bool(reproduced)

        defects: list[Defect] = []
        rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        for g in groups.values():
            g["tests"].sort(key=lambda x: (TECHNIQUE_RANK.get(x[0].technique, 4),
                                           rank[priorities[x[2].id]], x[0].id))
        ordered = sorted(groups.values(), key=lambda g: (
            SEVERITY_RANK[self._severity(g["kind"], g["tests"][0][2], g["tests"][0][1])],
            rank[priorities[g["tests"][0][2].id]]))
        for n, g in enumerate(ordered, start=1):
            defect = self._report(f"BUG-{n:03d}", g, priorities)
            defects.append(defect)
            for entry in g["entries"]:
                entry.defect_id = defect.id

        return DefectReport(triage=triage, defects=defects, clarifications_needed=clarifications)

    # ------------------------------------------------------------------ #
    def _classify(self, obs: Observation, tc: TestCase, req: Requirement,
                  retry: Optional[Observation]) -> tuple[str, str, str, str]:
        endpoint = f"{req.endpoint.method} {req.endpoint.path}" if req.endpoint else req.id
        if obs.status == "error":
            return "environment", f"응답을 받지 못함: {obs.actual}", "", ""

        failed, status = _first_failure(obs)
        if retry is not None and retry.status == "passed":
            if status in TRANSIENT:
                return ("environment", f"일시적 인프라 응답(HTTP {status}) — 재실행 시 통과 (flaky)", "", "")
            return ("test_bug", "재실행 시 통과 — 순서 의존 또는 비결정적 테스트로 의심", "", "")

        if tc.assumption and failed is not None and failed.type in ("elapsed_ms", "status"):
            return ("requirement_ambiguity",
                    f"테스트 오라클이 가정에 기반함: {tc.assumption}", "", "")

        if failed is None:
            return "test_bug", "실패로 기록됐지만 실패한 assertion이 없음", "", ""

        if failed.type == "no_5xx":
            return ("product_bug", f"서버 오류 HTTP {status} — 어떤 입력에도 5xx는 허용되지 않음",
                    f"{endpoint}|5xx|{status}", "server_error")
        if failed.type.startswith("same_as_previous"):
            key = failed.type.split(".", 1)[1]
            return ("product_bug", f"같은 요청 재시도에서 '{key}'가 달라짐 — 중복 처리",
                    f"{endpoint}|idempotency|{key}", "idempotency")

        expected_status = failed.expected if failed.type == "status" else None
        validation = next((e.status for e in req.errors if e.when == "validation"), 400)
        if failed.type == "status" and expected_status == validation and status != validation:
            return ("product_bug", f"검증되어야 할 입력이 HTTP {status}로 통과 — 입력 검증 누락",
                    f"{endpoint}|validation_bypass|{tc.focus}", "validation_bypass")
        if failed.type == "status_not_in" and req.success_status in (failed.expected or []):
            return ("product_bug", f"거부되어야 할 요청이 HTTP {status}로 성공",
                    f"{endpoint}|unexpected_success|{tc.focus}", "unexpected_success")
        if failed.type == "status" and status == validation and expected_status != validation:
            data = {}
            for s in tc.steps:
                data.update(s.body or {})
                data.update(s.query or {})
            broken = _violates(data, req.inputs)
            if broken:
                return "test_bug", f"테스트 데이터가 명세의 입력 규칙을 위반함: {broken}", "", ""
            return ("product_bug", f"명세상 유효한 입력이 HTTP {status}로 거부됨",
                    f"{endpoint}|valid_rejected|{tc.focus}", "valid_rejected")
        if (failed.type == "status" and isinstance(expected_status, int) and status is not None
                and 400 <= expected_status < 500 and 400 <= status < 500):
            return ("spec_mismatch",
                    f"명세는 HTTP {expected_status}, 실제는 HTTP {status} — 둘 다 거부 응답", "", "")
        if failed.type == "elapsed_ms":
            return ("product_bug", f"응답시간 기준 초과: {failed.actual}ms",
                    f"{endpoint}|performance", "performance")
        return ("product_bug", f"{failed.type}: 기대 {failed.expected}, 실제 {failed.actual}",
                f"{endpoint}|{failed.type}|{status}", "contract")

    @staticmethod
    def _severity(kind: str, req: Requirement, obs: Observation) -> str:
        money = req.business.get("money", False)
        security = req.business.get("security", False)
        if kind == "idempotency":
            return "critical" if money else "high"
        if kind in ("server_error", "unexpected_success"):
            return "high"
        if kind == "validation_bypass":
            return "high" if money else "medium"
        if kind == "valid_rejected":
            return "high" if money or security else "medium"
        if kind == "performance":
            return "low"
        return "medium"

    def _report(self, bug_id: str, g: dict, priorities: dict[str, str]) -> Defect:
        tc, obs, req = g["tests"][0]
        severity = self._severity(g["kind"], req, obs)
        risk_rank = int(priorities[req.id][1])
        priority = f"P{min(3, math.ceil((SEVERITY_RANK[severity] + risk_rank) / 2))}"

        failed, status = _first_failure(obs)
        outcome = {
            "server_error": f"HTTP {status} 서버 오류 발생",
            "idempotency": "같은 요청이 중복 처리됨",
            "validation_bypass": f"입력 검증 없이 HTTP {status} 응답",
            "unexpected_success": f"거부되어야 할 요청이 HTTP {status}로 성공",
            "valid_rejected": f"유효한 입력이 HTTP {status}로 거부됨",
            "performance": "응답시간 기준 초과",
        }.get(g["kind"], "응답이 명세와 다름")

        repro = []
        if obs.step_results and any(s.auth for s in tc.steps):
            repro.append("테스트 계정으로 로그인해 토큰을 발급받는다")
        for i, s in enumerate(tc.steps, start=1):
            payload = _readable(s.body if s.body is not None else (s.query or {}))
            extra = f", 헤더 {list(s.headers)}" if s.headers else ""
            times = f" — {s.repeat}회 반복" if s.repeat > 1 else ""
            repro.append(f"{s.method} {s.path} 요청 (데이터 {payload}{extra}){times}")

        confidence = {"server_error": 0.95, "idempotency": 0.92, "validation_bypass": 0.88,
                      "unexpected_success": 0.88, "valid_rejected": 0.75, "performance": 0.7}.get(g["kind"], 0.7)
        if g["reproduced"]:
            confidence += 0.03
        else:
            confidence -= 0.2
        confidence += 0.005 * (len(g["tests"]) - 1)

        return Defect(
            id=bug_id,
            title=f"{req.feature_name}: {tc.title.removeprefix(req.feature_name).strip()} 시 {outcome}",
            req_id=req.id,
            severity=severity,
            priority=priority,
            reproduction=repro,
            expected=obs.expected,
            actual=obs.actual,
            evidence=sorted(set(g["evidence"])),
            related_tests=[t.id for t, _, _ in g["tests"]],
            reproducible=g["reproduced"],
            confidence=round(min(0.99, max(0.1, confidence)), 2),
        )
