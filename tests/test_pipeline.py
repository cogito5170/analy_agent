"""End-to-end: run all eight agents against the demo app and check the seeded defects."""

import json
import tempfile
import unittest
from pathlib import Path

from demo.target_app import start
from qa_agents.orchestrator import Pipeline

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / "demo/spec/mini_shop.json").read_text())
CLAIMS = json.loads((ROOT / "demo/claims.json").read_text())


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, base_url = start()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.run_dir = Path(cls.tmp.name)
        cls.board = Pipeline(SPEC, cls.run_dir, base_url=base_url, claims=CLAIMS,
                             project_root=ROOT).run()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_every_stage_wrote_its_contract(self):
        names = sorted(p.name for p in self.run_dir.glob("0*.json"))
        self.assertEqual(len(names), 8)
        trace = json.loads((self.run_dir / "pipeline_trace.json").read_text())
        self.assertEqual([s["produces"] for s in trace["stages"]][-1], "qa_portfolio/1")

    def test_seeded_product_defects_are_found(self):
        defects = self.board["qa_defect/1"].defects
        titles = " ".join(d.title for d in defects)
        self.assertIn("중복 처리", titles)                       # idempotency
        self.assertIn("최솟값-1(0)", titles)                      # amount = 0
        self.assertIn("잘못된 비밀번호 시 HTTP 500", titles)        # wrong password crash
        critical = [d for d in defects if d.severity == "critical"]
        self.assertEqual(len(critical), 1)
        self.assertTrue(all(d.reproducible for d in defects))

    def test_non_bugs_are_not_reported_as_bugs(self):
        triage = {t.test_id: t for t in self.board["qa_defect/1"].triage}
        perf = next(t for t in self.board["qa_test_plan/1"].test_cases if t.technique == "performance")
        self.assertEqual(triage[perf.id].classification, "requirement_ambiguity")
        self.assertIsNotNone(triage[perf.id].transient_noise)   # the cold-start 503

    def test_reviewer_flags_checks_masked_by_the_crash(self):
        checks = {f.check for f in self.board["qa_review/1"].findings}
        self.assertIn("blocked_by_defect", checks)
        self.assertIn("requirement_coverage", checks)            # account deletion is untestable
        self.assertEqual(self.board["qa_review/1"].verdict, "conditional_pass")

    def test_portfolio_excludes_unmeasured_claims(self):
        portfolio = self.board["qa_portfolio/1"]
        self.assertIn("테스트 자동화로 QA 시간을 43% 절감했다", portfolio.excluded_claims)
        result = next(s for s in portfolio.sections if s.key == "result")
        kept = result.body.split("포트폴리오에서 제외한 주장")[0]
        self.assertNotIn("43%", kept)
        self.assertTrue((self.run_dir / "portfolio.md").exists())

    def test_evidence_files_exist_for_every_defect(self):
        for d in self.board["qa_defect/1"].defects:
            for e in d.evidence:
                self.assertTrue((self.run_dir / e).exists(), e)


class PhaseTests(unittest.TestCase):
    def test_phase_one_stops_after_defect_analysis(self):
        server, base_url = start()
        try:
            with tempfile.TemporaryDirectory() as d:
                board = Pipeline(SPEC, Path(d), base_url=base_url).run(phase=1)
        finally:
            server.shutdown()
            server.server_close()
        self.assertIn("qa_defect/1", board)
        self.assertNotIn("qa_review/1", board)


if __name__ == "__main__":
    unittest.main()
