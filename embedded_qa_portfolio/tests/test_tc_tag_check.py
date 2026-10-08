import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import tc_tag_check  # noqa: E402

GOOD = """
/* @verifies SWR-002 — boundaries */
static void test_a(void) {}

/* @verifies SWR-004, SWR-012 */
void test_b(void) {}

static void helper(void) {}

int main(void) { RUN_TEST(test_a); RUN_TEST(test_b); }
"""


class TcTagCheckTests(unittest.TestCase):
    def scan(self, source):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            Path(d, "test_x.c").write_text(source)
            funcs, errors = tc_tag_check.scan(Path(d))
        return funcs, {e.split()[0] for e in errors}

    def test_tags_are_read(self):
        funcs, errors = self.scan(GOOD)
        self.assertEqual(errors, set())
        self.assertEqual([f.verifies for f in funcs], [["SWR-002"], ["SWR-004", "SWR-012"]])

    def test_missing_tag(self):
        source = GOOD.replace("/* @verifies SWR-002 — boundaries */\n", "")
        self.assertIn("T01", self.scan(source)[1])

    def test_tag_must_be_directly_above(self):
        source = GOOD.replace("/* @verifies SWR-002 — boundaries */\n",
                              "/* @verifies SWR-002 */\nstatic int x;\n")
        self.assertIn("T01", self.scan(source)[1])

    def test_unregistered_test(self):
        self.assertIn("T03", self.scan(GOOD.replace("RUN_TEST(test_b);", ""))[1])

    def test_project_tests_pass(self):
        self.assertEqual(tc_tag_check.main([]), 0)


if __name__ == "__main__":
    unittest.main()
