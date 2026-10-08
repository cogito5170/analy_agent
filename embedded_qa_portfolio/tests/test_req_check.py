import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import req_check  # noqa: E402

GOOD = {
    "safety_goals": [{"id": "SG-01", "text": "x", "asil": "D", "safe_state": "컨택터 개방"}],
    "features": [{"id": "FN-01", "text": "x"}],
    "requirements": [
        {"id": "SWR-001", "text": "전압이 4.25 V를 초과하면 고장으로 판정해야 한다.",
         "parent": ["SG-01", "FN-01"], "method": "test", "priority": "must"},
    ],
}


def with_req(**changes):
    data = {k: [dict(i) for i in v] for k, v in GOOD.items()}
    data["requirements"][0].update(changes)
    return data


def codes(data):
    errors, warnings = req_check.check(data)
    return {e.code for e in errors}, {w.code for w in warnings}


class ReqCheckTests(unittest.TestCase):
    def test_clean_input_has_no_issues(self):
        self.assertEqual(codes(GOOD), (set(), set()))

    def test_each_rule_fires(self):
        cases = {
            "E01": with_req(id="REQ-1"),
            "E02": with_req(parent=["SG-99"]),
            "E03": with_req(method="inspection"),
            "E04": with_req(text="결과는 빠르게 4 ms 안에 표시해야 한다."),
            "E05": with_req(text="전압이 높으면 고장으로 판정해야 한다."),
            "E06": with_req(text="전압이 4.25 V를 넘으면 고장이다."),
        }
        for code, data in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, codes(data)[0])

    def test_safety_goal_rules(self):
        data = with_req()
        data["safety_goals"][0]["asil"] = "E"
        self.assertIn("E07", codes(data)[0])
        data = with_req(parent=["FN-01"])
        self.assertIn("E08", codes(data)[0])

    def test_duplicate_id(self):
        data = with_req()
        data["requirements"].append(dict(data["requirements"][0]))
        self.assertIn("E01", codes(data)[0])

    def test_compound_requirement_warns(self):
        data = with_req(text="4 V를 넘으면 판정해야 하며 보고해야 한다.")
        self.assertIn("W01", codes(data)[1])

    def test_project_requirements_pass(self):
        errors, _ = req_check.check(req_check.load(ROOT / "requirements"))
        self.assertEqual(errors, [], [f"{e.code} {e.target} {e.message}" for e in errors])


if __name__ == "__main__":
    unittest.main()
