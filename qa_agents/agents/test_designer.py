"""Test Designer — derives test cases from requirements with named techniques.

The technique set for a requirement comes from the depth the Risk Analyst
assigned. Every case records which technique produced it and what its oracle
is, so a reviewer can tell why the case exists. Cases that would send the same
request with the same expectation are merged and keep the extra techniques in
``also_covers`` instead of being run twice.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, Optional

from ..contracts import (
    Expectation,
    InputField,
    Requirement,
    RequirementAnalysis,
    RiskAnalysis,
    Skipped,
    Step,
    TestCase,
    TestPlan,
)
from .base import Agent, Board

DEPTH_TECHNIQUES = {
    "smoke": ["happy_path", "negative"],
    "standard": ["happy_path", "negative", "equivalence_partitioning", "boundary_value"],
    "thorough": ["happy_path", "negative", "equivalence_partitioning", "boundary_value",
                 "decision_table", "security_negative"],
    "exhaustive": ["happy_path", "negative", "equivalence_partitioning", "boundary_value",
                   "decision_table", "security_negative", "exploratory"],
}
INJECTION = ["' OR '1'='1' --", "<script>alert(1)</script>"]
ASSUMED_RESPONSE_MS = 500


def _sized(field: InputField, length: int) -> str:
    if field.type == "email":
        domain = "@example.com"
        return "a" * max(1, length - len(domain)) + domain if length > len(domain) else "a" * length
    return "P" * length


class TestDesigner(Agent):
    name = "Test Designer"
    consumes = ("qa_requirement/1", "qa_risk/1")
    produces = "qa_test_plan/1"

    def run(self, board: Board) -> TestPlan:
        analysis: RequirementAnalysis = board["qa_requirement/1"]
        risk: RiskAnalysis = board["qa_risk/1"]
        by_req = {r.req_id: r for r in risk.risks}

        cases: list[TestCase] = []
        strategy: dict[str, list[str]] = {}
        skipped: list[Skipped] = []
        counters: dict[str, int] = {}

        # Design highest-risk requirements first so their cases get the lowest IDs.
        for req in sorted(analysis.requirements, key=lambda r: -by_req[r.id].risk_score):
            r = by_req[req.id]
            if not req.testable or req.endpoint is None:
                skipped.append(Skipped(req_id=req.id, reason="요구사항이 테스트 가능하지 않음 (Requirement Analyst 판정)"))
                continue
            techniques = self._techniques(req, r.test_depth)
            strategy[req.id] = techniques
            for draft in self._design(req, techniques):
                draft["priority"] = r.priority
                self._add(cases, draft, req, counters)

        return TestPlan(strategy=strategy, test_cases=cases, skipped_requirements=skipped)

    # ------------------------------------------------------------------ #
    def _techniques(self, req: Requirement, depth: str) -> list[str]:
        if req.type == "business_rule":
            return ["state_transition"]
        if req.type == "non_functional":
            return ["performance"]
        techniques = list(DEPTH_TECHNIQUES[depth])
        if not req.inputs:
            techniques = [t for t in techniques if t in ("happy_path", "negative", "exploratory")]
        if "decision_table" in techniques and sum(f.required for f in req.inputs) < 2:
            techniques.remove("decision_table")
        return techniques

    def _add(self, cases: list[TestCase], draft: dict, req: Requirement, counters: dict) -> None:
        signature = json.dumps([s.model_dump() for s in draft.get("steps", [])], sort_keys=True)
        if draft.get("automated", True):
            for existing in cases:
                if existing.automated and existing.req_id == req.id and json.dumps(
                    [s.model_dump() for s in existing.steps], sort_keys=True
                ) == signature:
                    if draft["technique"] != existing.technique and draft["technique"] not in existing.also_covers:
                        existing.also_covers.append(draft["technique"])
                    return
        n = counters.get(req.feature, 0) + 1
        counters[req.feature] = n
        cases.append(TestCase(id=f"TC-{req.feature.upper()}-{n:03d}", req_id=req.id,
                              automated=draft.pop("automated", True), **draft))

    def _step(self, req: Requirement, data: Optional[dict], expect: Expectation,
              auth: Optional[bool] = None, headers: Optional[dict] = None, repeat: int = 1) -> Step:
        body: dict[str, Any] = {}
        query: dict[str, Any] = {}
        locations = {f.name: f.location for f in req.inputs}
        for k, v in (data or {}).items():
            (query if locations.get(k) == "query" else body)[k] = v
        has_body = req.endpoint.method.upper() not in ("GET", "DELETE")
        return Step(
            method=req.endpoint.method,
            path=req.endpoint.path,
            body=body if has_body and (body or data is not None) else None,
            query=query or None,
            headers=headers or {},
            auth=req.requires_auth if auth is None else auth,
            repeat=repeat,
            expect=expect,
        )

    def _validation_status(self, req: Requirement) -> tuple[int, Optional[str]]:
        for e in req.errors:
            if e.when == "validation":
                return e.status, None
        return 400, "입력 검증 실패 응답이 명세에 없어 400으로 가정"

    def _success(self, req: Requirement) -> Expectation:
        return Expectation(status=req.success_status, body_contains=req.success_body,
                           body_has_keys=req.success_keys)

    # ------------------------------------------------------------------ #
    def _design(self, req: Requirement, techniques: list[str]) -> list[dict]:
        drafts: list[dict] = []
        name = req.feature_name
        example = dict(req.valid_example)
        v_status, v_assumption = self._validation_status(req)
        invalid = Expectation(status=v_status)
        in_bounds = Expectation(status_not_in=[v_status])

        def case(title, technique, steps, oracle, focus=None, assumption=None):
            drafts.append(dict(title=title, technique=technique, steps=steps, oracle=oracle,
                               focus=focus, assumption=assumption))

        if "happy_path" in techniques:
            case(f"{name} 유효한 입력으로 요청", "happy_path",
                 [self._step(req, example, self._success(req))],
                 f"status {req.success_status} 및 성공 응답 본문")

        if "negative" in techniques:
            for err in req.errors:
                if err.when == "validation":
                    if "equivalence_partitioning" not in techniques and req.inputs:
                        case(f"{name} 입력 없이 요청", "negative",
                             [self._step(req, {}, invalid)], f"status {v_status}",
                             assumption=v_assumption)
                    continue
                if err.input:
                    case(f"{name} {err.description or err.when}", "negative",
                         [self._step(req, {**example, **err.input}, Expectation(status=err.status))],
                         f"status {err.status}", focus=",".join(err.input))
                elif req.requires_auth and err.status == 401:
                    case(f"{name} 인증 없이 요청", "negative",
                         [self._step(req, example, Expectation(status=401), auth=False)],
                         "status 401")

        if "equivalence_partitioning" in techniques:
            for f in req.inputs:
                if f.required:
                    data = {k: v for k, v in example.items() if k != f.name}
                    case(f"{name} 필수 입력 '{f.name}' 누락", "equivalence_partitioning",
                         [self._step(req, data, invalid)], f"status {v_status}", f.name, v_assumption)
                wrong = {"integer": "abc", "number": "abc", "string": 12345, "email": "not-an-email"}[f.type]
                label = "형식이 잘못된 이메일" if f.type == "email" else "잘못된 타입의 값"
                case(f"{name} '{f.name}'에 {label}", "equivalence_partitioning",
                     [self._step(req, {**example, f.name: wrong}, invalid)],
                     f"status {v_status}", f.name, v_assumption)

        if "boundary_value" in techniques:
            for f in req.inputs:
                points: list[tuple[Any, str, bool]] = []
                if f.min_length is not None:
                    points += [(f.min_length - 1, "최소 길이-1", False), (f.min_length, "최소 길이", True)]
                if f.max_length is not None:
                    points += [(f.max_length, "최대 길이", True), (f.max_length + 1, "최대 길이+1", False)]
                for length, label, ok in points:
                    if length < 0:
                        continue
                    case(f"{name} '{f.name}' {label}({length}자)", "boundary_value",
                         [self._step(req, {**example, f.name: _sized(f, length)},
                                     in_bounds if ok else invalid)],
                         f"status {'≠' if ok else '='} {v_status}", f.name, v_assumption)
                nums: list[tuple[Any, str, bool]] = []
                if f.minimum is not None:
                    lo = int(f.minimum)
                    nums += [(lo - 1, "최솟값-1", False), (lo, "최솟값", True)]
                if f.maximum is not None:
                    hi = int(f.maximum)
                    nums += [(hi, "최댓값", True), (hi + 1, "최댓값+1", False)]
                for value, label, ok in nums:
                    expect = self._success(req) if ok else invalid
                    case(f"{name} '{f.name}' {label}({value})", "boundary_value",
                         [self._step(req, {**example, f.name: value}, expect)],
                         f"status {expect.status}", f.name, v_assumption)

        if "decision_table" in techniques:
            required = [f.name for f in req.inputs if f.required][:3]
            for row in itertools.product([True, False], repeat=len(required)):
                data = {k: v for k, v in example.items()
                        if k not in required or row[required.index(k)]}
                ok = all(row)
                desc = ", ".join(f"{n}={'O' if present else 'X'}" for n, present in zip(required, row))
                case(f"{name} 결정 테이블 [{desc}]", "decision_table",
                     [self._step(req, data, self._success(req) if ok else invalid)],
                     "모든 필수 입력이 있을 때만 성공", assumption=None if ok else v_assumption)

        if "security_negative" in techniques:
            sensitive = req.business.get("security", False)
            for f in req.inputs:
                if f.type not in ("string", "email"):
                    continue
                for payload in INJECTION:
                    expect = (Expectation(status_not_in=[req.success_status]) if sensitive
                              else Expectation())
                    case(f"{name} '{f.name}'에 주입 문자열 입력", "security_negative",
                         [self._step(req, {**example, f.name: payload}, expect)],
                         "인증 우회 없음, 5xx 없음" if sensitive else "5xx 없음", f.name)

        if "state_transition" in techniques and req.rule is not None:
            rule = req.rule
            if rule.kind == "threshold_lock":
                attempt = {**example, **rule.input}
                case(f"{name} {rule.threshold}회 실패 후 잠금 상태 전이", "state_transition", [
                    self._step(req, attempt, Expectation(status_not_in=[req.success_status]),
                               repeat=rule.threshold),
                    self._step(req, attempt, Expectation(status=rule.status)),
                ], f"{rule.threshold}회 실패까지는 거부, 이후 status {rule.status}")
            elif rule.kind == "idempotent":
                headers = {rule.header: f"qa-{req.id.lower()}-key"}
                first = self._success(req)
                again = first.model_copy(update={"same_as_previous": rule.key})
                case(f"{name} 같은 {rule.header}로 재시도", "state_transition", [
                    self._step(req, example, first, headers=headers),
                    self._step(req, example, again, headers=headers),
                ], f"두 응답의 '{rule.key}'가 같아야 함 (중복 처리 없음)", rule.header)

        if "performance" in techniques:
            limit = req.max_response_ms or ASSUMED_RESPONSE_MS
            assumption = None if req.max_response_ms else (
                f"요구사항에 정량 기준이 없어 {ASSUMED_RESPONSE_MS}ms로 가정 — 명확화 필요")
            expect = self._success(req).model_copy(update={"max_elapsed_ms": limit})
            case(f"{name} 응답 시간 {limit}ms 이내", "performance",
                 [self._step(req, example, expect, repeat=3)],
                 f"3회 모두 {limit}ms 이내", assumption=assumption)

        if "exploratory" in techniques:
            drafts.append(dict(
                title=f"{name} 탐색적 테스트 차터", technique="exploratory", automated=False,
                steps=[], oracle="테스터 판단 (세션 노트로 기록)",
                charter=(f"60분 동안 {name} 기능을 대상으로 세션 만료, 동시 요청, 뒤로가기/재전송, "
                         "다국어·특수문자 입력을 탐색해 자동화 케이스가 놓친 위험을 찾는다."),
            ))
        return drafts
