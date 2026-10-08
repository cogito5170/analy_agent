import copy
import json
import tempfile
import unittest
from pathlib import Path

from qa_agents.agents.defect_analyst import DefectAnalyst
from qa_agents.agents.evidence_analyst import EvidenceAnalyst
from qa_agents.agents.requirement_analyst import RequirementAnalyst, _threshold_ms, _vague_terms
from qa_agents.agents.risk_analyst import RiskAnalyst
from qa_agents.agents.test_designer import TestDesigner
from qa_agents.contracts import (
    AssertionResult,
    ContractError,
    Observation,
    ObservationReport,
    StepResult,
    check_references,
    load,
)

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "demo/spec/mini_shop.json").read_text())


def design(spec=SPEC):
    board = {}
    board["qa_requirement/1"] = RequirementAnalyst(spec).run(board)
    board["qa_risk/1"] = RiskAnalyst().run(board)
    board["qa_test_plan/1"] = TestDesigner().run(board)
    return board


class ContractTests(unittest.TestCase):
    def test_unknown_schema_is_rejected(self):
        with self.assertRaises(ContractError):
            load({"schema": "qa_requirement/2"})

    def test_unknown_field_is_rejected(self):
        doc = design()["qa_risk/1"].to_json()
        doc["surprise"] = 1
        with self.assertRaises(Exception):
            load(doc)

    def test_broken_reference_is_reported(self):
        board = design()
        board["qa_test_plan/1"].test_cases[0].req_id = "REQ-999"
        self.assertTrue(any("REQ-999" in p for p in check_references(board)))


class RequirementAnalystTests(unittest.TestCase):
    def test_vague_terms(self):
        self.assertIn("빠르게", _vague_terms("결과는 빠르게 표시된다"))
        self.assertIn("등", _vague_terms("이메일, 전화번호 등을 입력한다"))
        self.assertEqual(_vague_terms("회원 등록을 완료한다"), [])

    def test_threshold_parsing(self):
        self.assertEqual(_threshold_ms("300ms 이내"), 300)
        self.assertEqual(_threshold_ms("2초 이내"), 2000)
        self.assertIsNone(_threshold_ms("빠르게"))

    def test_untestable_feature_is_flagged(self):
        analysis = design()["qa_requirement/1"]
        withdraw = next(r for r in analysis.requirements if r.feature == "withdraw")
        self.assertFalse(withdraw.testable)
        self.assertFalse(analysis.testable)
        self.assertTrue(any(m.req_id == withdraw.id and m.category == "interface"
                            for m in analysis.missing_requirements))

    def test_missing_boundary_is_reported(self):
        spec = copy.deepcopy(SPEC)
        del spec["features"][0]["inputs"][1]["max_length"]
        analysis = RequirementAnalyst(spec).run({})
        self.assertTrue(any(m.category == "boundary" and "password" in m.description
                            for m in analysis.missing_requirements))

    def test_rules_become_child_requirements(self):
        analysis = design()["qa_requirement/1"]
        rules = [r for r in analysis.requirements if r.type == "business_rule"]
        self.assertEqual({r.rule.kind for r in rules}, {"threshold_lock", "idempotent"})
        self.assertTrue(all(r.parent for r in rules))


class RiskAnalystTests(unittest.TestCase):
    def test_formula_and_ordering(self):
        risks = design()["qa_risk/1"].risks
        for r in risks:
            expected = r.impact.value * (0.6 * r.likelihood.value + 0.4 * (1 - r.detectability.value))
            self.assertAlmostEqual(r.risk_score, round(expected, 3))
        self.assertEqual(risks, sorted(risks, key=lambda r: -r.risk_score))
        targets = [r.target for r in risks]
        self.assertLess(targets.index("결제 (functional)"), targets.index("내 정보 조회 (functional)"))
        self.assertEqual(risks[0].priority, "P0")


class TestDesignerTests(unittest.TestCase):
    def setUp(self):
        self.board = design()
        self.plan = self.board["qa_test_plan/1"]

    def test_boundary_values_for_amount(self):
        amounts = sorted(s.body["amount"] for t in self.plan.test_cases
                         if t.technique == "boundary_value" and t.focus == "amount" for s in t.steps)
        self.assertEqual(amounts, [0, 1, 1000000, 1000001])

    def test_untestable_requirement_is_skipped(self):
        withdraw = next(r.id for r in self.board["qa_requirement/1"].requirements if r.feature == "withdraw")
        self.assertIn(withdraw, [s.req_id for s in self.plan.skipped_requirements])

    def test_identical_cases_are_merged(self):
        signatures = [json.dumps([s.model_dump() for s in t.steps], sort_keys=True) + t.req_id
                      for t in self.plan.test_cases if t.automated]
        self.assertEqual(len(signatures), len(set(signatures)))
        self.assertTrue(any("decision_table" in t.also_covers for t in self.plan.test_cases))

    def test_unquantified_performance_uses_flagged_assumption(self):
        perf = next(t for t in self.plan.test_cases if t.technique == "performance")
        self.assertIsNotNone(perf.assumption)


def observation(tc, status, http_status, failed_type, expected=None):
    assertions = [AssertionResult(type=failed_type, expected=expected, actual=http_status, passed=False)]
    return Observation(
        test_id=tc.id, req_id=tc.req_id, status=status, expected="x", actual="y",
        step_results=[StepResult(step=0, iteration=0, request={}, elapsed_ms=1,
                                 response={"status": http_status, "body": {}}, assertions=assertions)],
        evidence=[f"evidence/{tc.id}.json"])


class DefectAnalystTests(unittest.TestCase):
    def setUp(self):
        self.board = design()
        self.cases = {t.id: t for t in self.board["qa_test_plan/1"].test_cases}

    def triage(self, obs, rerun_result=None):
        board = dict(self.board)
        board["qa_observation/1"] = ObservationReport(environment={}, summary={}, observations=[obs])
        rerun = (lambda tc: rerun_result) if rerun_result is not None else (lambda tc: obs)
        return DefectAnalyst(rerun=rerun).run(board)

    def case(self, technique, feature="LOGIN"):
        return next(t for t in self.cases.values()
                    if t.technique == technique and t.id.startswith(f"TC-{feature}"))

    def test_server_error_is_product_bug(self):
        tc = self.case("negative")
        report = self.triage(observation(tc, "failed", 500, "no_5xx"))
        self.assertEqual(report.triage[0].classification, "product_bug")
        self.assertEqual(report.defects[0].severity, "high")

    def test_transient_failure_that_passes_on_rerun_is_environment(self):
        tc = self.case("negative")
        passed = Observation(test_id=tc.id, req_id=tc.req_id, status="passed", expected="", actual="")
        report = self.triage(observation(tc, "failed", 503, "no_5xx"), passed)
        self.assertEqual(report.triage[0].classification, "environment")
        self.assertEqual(report.defects, [])

    def test_non_transient_flake_is_test_bug(self):
        tc = self.case("negative")
        passed = Observation(test_id=tc.id, req_id=tc.req_id, status="passed", expected="", actual="")
        report = self.triage(observation(tc, "failed", 401, "status", 403), passed)
        self.assertEqual(report.triage[0].classification, "test_bug")

    def test_different_rejection_code_is_spec_mismatch(self):
        tc = self.case("negative")
        report = self.triage(observation(tc, "failed", 403, "status", 401))
        self.assertEqual(report.triage[0].classification, "spec_mismatch")
        self.assertEqual(len(report.clarifications_needed), 1)

    def test_assumed_oracle_failure_is_requirement_ambiguity(self):
        tc = self.case("performance", "SEARCH")
        report = self.triage(observation(tc, "failed", 200, "elapsed_ms", "<= 500"))
        self.assertEqual(report.triage[0].classification, "requirement_ambiguity")

    def test_validation_bypass_on_money_is_high(self):
        tc = next(t for t in self.cases.values() if t.title.endswith("최솟값-1(0)"))
        report = self.triage(observation(tc, "failed", 200, "status", 400))
        self.assertEqual(report.defects[0].severity, "high")


class EvidenceAnalystTests(unittest.TestCase):
    def grade(self, claim):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "04_observation.json").write_text("{}")
            analyst = EvidenceAnalyst(Path(d), {}, [], ROOT)
            return analyst._grade_user_claim(claim, {"12", "75"})

    def test_unmeasured_number_is_unsupported(self):
        c = self.grade({"claim": "시간을 43% 절감했다", "evidence": ["run:04_observation.json"]})
        self.assertEqual(c.strength, "unsupported")

    def test_measured_number_with_execution_log_is_strong(self):
        c = self.grade({"claim": "테스트 12개를 실행했다", "evidence": ["run:04_observation.json"]})
        self.assertEqual(c.strength, "strong")

    def test_missing_artifact_and_prose_only(self):
        self.assertEqual(self.grade({"claim": "x", "evidence": ["nope.py"]}).strength, "unsupported")
        self.assertEqual(self.grade({"claim": "x", "evidence": []}).strength, "unsupported")
        self.assertEqual(self.grade({"claim": "x", "evidence": ["README.md"]}).strength, "weak")


if __name__ == "__main__":
    unittest.main()
