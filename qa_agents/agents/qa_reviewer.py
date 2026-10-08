"""QA Reviewer — reviews the QA work itself, not the product.

It audits the outputs of the other agents the way a QA lead reviews a junior's
work: uncovered requirements, expected results with no basis in the spec, weak
oracles that could hide bugs (false negatives), defects that are not
reproducible or lack evidence (false positives), duplicate or excessive tests,
and tests that are themselves broken.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..contracts import (
    DefectReport,
    Finding,
    ObservationReport,
    RequirementAnalysis,
    Review,
    RiskAnalysis,
    TestPlan,
)
from .base import Agent, Board

NEGATIVE_TECHNIQUES = {"negative", "equivalence_partitioning", "boundary_value", "decision_table"}
P3_TEST_BUDGET = 6


class QAReviewer(Agent):
    name = "QA Reviewer"
    consumes = ("qa_requirement/1", "qa_risk/1", "qa_test_plan/1", "qa_observation/1", "qa_defect/1")
    produces = "qa_review/1"

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)

    def run(self, board: Board) -> Review:
        req: RequirementAnalysis = board["qa_requirement/1"]
        risk: RiskAnalysis = board["qa_risk/1"]
        plan: TestPlan = board["qa_test_plan/1"]
        obs: ObservationReport = board["qa_observation/1"]
        dfx: DefectReport = board["qa_defect/1"]

        findings: list[Finding] = []

        def find(check, severity, target, message):
            findings.append(Finding(id=f"RV-{len(findings) + 1:03d}", check=check,
                                    severity=severity, target=target, message=message))

        prio = {r.req_id: r.priority for r in risk.risks}
        reqs = {r.id: r for r in req.requirements}
        by_req: dict[str, list] = {}
        for tc in plan.test_cases:
            by_req.setdefault(tc.req_id, []).append(tc)
        results = {o.test_id: o for o in obs.observations}
        skipped = {s.req_id for s in plan.skipped_requirements}

        # 1. Requirement coverage
        for r in req.requirements:
            automated = [t for t in by_req.get(r.id, []) if t.automated]
            if r.id in skipped:
                find("requirement_coverage", "major", r.id,
                     f"{r.feature_name}: 요구사항이 테스트 불가 상태라 검증되지 않음 — 명세 보완 후 재설계 필요")
            elif not automated:
                find("requirement_coverage", "blocker", r.id,
                     f"{r.feature_name}: 테스트 가능한 요구사항에 자동화 테스트가 없음")

        # 2. Negative coverage for high-risk functional requirements
        for r in req.requirements:
            if r.type != "functional" or r.id in skipped or prio[r.id] not in ("P0", "P1"):
                continue
            used = {t.technique for t in by_req.get(r.id, [])} | {
                c for t in by_req.get(r.id, []) for c in t.also_covers}
            if r.inputs and not used & NEGATIVE_TECHNIQUES:
                find("negative_coverage", "major", r.id,
                     f"{prio[r.id]} 요구사항에 부정/경계 테스트가 없음")

        # 3. Expected results must come from the spec, or be flagged as assumptions
        for tc in plan.test_cases:
            r = reqs[tc.req_id]
            declared = {r.success_status, *(e.status for e in r.errors)}
            if r.rule and r.rule.status:
                declared.add(r.rule.status)
            for s in tc.steps:
                if s.expect.status is not None and s.expect.status not in declared and not tc.assumption:
                    find("expected_result_basis", "major", tc.id,
                         f"기대 status {s.expect.status}가 명세에 근거하지 않음")
            if tc.assumption:
                find("assumption", "info", tc.id, f"가정에 기반한 오라클: {tc.assumption}")

        # 4. Duplicates
        seen: dict[str, str] = {}
        for tc in plan.test_cases:
            if not tc.automated:
                continue
            key = tc.req_id + json.dumps([s.model_dump() for s in tc.steps], sort_keys=True)
            if key in seen:
                find("duplicate_test", "minor", tc.id, f"{seen[key]}와 동일한 요청/기대값")
            seen.setdefault(key, tc.id)

        # 5. Over-testing low-risk requirements
        for req_id, tcs in by_req.items():
            if prio[req_id] == "P3" and sum(t.automated for t in tcs) > P3_TEST_BUDGET:
                find("over_testing", "minor", req_id,
                     f"P3 요구사항에 테스트 {len(tcs)}개 — 예산({P3_TEST_BUDGET}) 초과")

        # 6. Weak oracles on passing tests (false-negative risk)
        weak = []
        for tc in plan.test_cases:
            o = results.get(tc.id)
            if o is None or o.status != "passed":
                continue
            explicit = [a for r in o.step_results for a in r.assertions if a.type != "no_5xx"]
            if not explicit:
                weak.append(tc.id)
        if weak:
            find("weak_oracle", "minor", ",".join(weak),
                 f"통과한 테스트 {len(weak)}개가 '5xx 없음'만 확인함 — 잘못된 성공을 놓칠 수 있음")

        # 7. Defects: evidence, reproducibility, confidence (false-positive risk)
        for d in dfx.defects:
            missing = [e for e in d.evidence if not (self.run_dir / e).exists()]
            if not d.evidence or missing:
                find("defect_evidence", "blocker", d.id, f"증거 파일 없음: {missing or '없음'}")
            if not d.reproducible:
                find("defect_reproducibility", "major", d.id, "재실행에서 재현되지 않은 결함 — 오탐 가능성")
            if d.confidence < 0.7:
                find("defect_confidence", "major", d.id, f"신뢰도 {d.confidence} — 추가 확인 필요")
            # A crash ends a test before its own oracle runs, so those checks never happened.
            masked = []
            for tid in d.related_tests[1:]:
                first = next((a for r in results[tid].step_results for a in r.assertions
                              if not a.passed), None)
                if first is not None and first.type == "no_5xx":
                    masked.append(tid)
            if masked:
                find("blocked_by_defect", "major", ",".join(masked),
                     f"{d.id}의 서버 오류에 가려 이 테스트들의 본래 검증(경계값·상태 전이 등)이 "
                     f"수행되지 않음 — {d.id} 수정 후 재실행 필요")

        # 8. Broken tests, flaky environment, open questions
        for t in dfx.triage:
            if t.transient_noise and t.classification != "environment":
                find("environment", "minor", t.test_id, f"일시적 환경 오류 감지: {t.transient_noise}")
            if t.classification == "test_bug":
                find("test_quality", "major", t.test_id, f"테스트 자체 결함: {t.reason}")
            elif t.classification == "environment":
                find("environment", "minor", t.test_id, f"환경 문제: {t.reason}")
            elif t.classification in ("requirement_ambiguity", "spec_mismatch"):
                find("open_question", "major", t.test_id,
                     f"판정 보류 ({t.classification}): {t.reason}")
        for o in obs.observations:
            if o.status == "not_run":
                find("not_run", "info", o.test_id, "수동 탐색 차터 — 세션 결과 기록 필요")

        executed = [o for o in obs.observations if o.status in ("passed", "failed")]
        covered = {o.req_id for o in executed}
        triage_counts: dict[str, int] = {}
        for t in dfx.triage:
            triage_counts[t.classification] = triage_counts.get(t.classification, 0) + 1
        techniques: dict[str, int] = {}
        for tc in plan.test_cases:
            for t in [tc.technique, *tc.also_covers]:
                techniques[t] = techniques.get(t, 0) + 1
        severities: dict[str, int] = {}
        for d in dfx.defects:
            severities[d.severity] = severities.get(d.severity, 0) + 1

        metrics = {
            "requirements_total": len(req.requirements),
            "requirements_testable": sum(r.testable for r in req.requirements),
            "requirements_executed": len(covered),
            "requirement_coverage": round(len(covered) / len(req.requirements), 3),
            "test_cases_total": len(plan.test_cases),
            "test_cases_automated": sum(t.automated for t in plan.test_cases),
            "tests_executed": len(executed),
            "tests_passed": sum(o.status == "passed" for o in executed),
            "tests_failed": sum(o.status == "failed" for o in executed),
            "techniques": techniques,
            "triage": triage_counts,
            "defects_by_severity": severities,
            "defects_total": len(dfx.defects),
        }
        blockers = any(f.severity == "blocker" for f in findings)
        majors = any(f.severity == "major" for f in findings)
        verdict = "fail" if blockers else "conditional_pass" if majors else "pass"
        return Review(verdict=verdict, metrics=metrics, findings=findings)
