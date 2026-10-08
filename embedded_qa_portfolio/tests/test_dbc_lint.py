import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import dbc_lint  # noqa: E402

DBC = (ROOT / "can/bms.dbc").read_text()
HEADER = (ROOT / "firmware/include/bms.h").read_text()


def errors(text=DBC, header=None):
    db = dbc_lint.parse(text)
    found = dbc_lint.check(db)
    if header is not None:
        found += dbc_lint.check_header(db, header)
    return {e.split()[0] for e in found}


class DbcLintTests(unittest.TestCase):
    def test_project_database_is_clean(self):
        self.assertEqual(errors(header=HEADER), set())

    def test_parser_reads_everything(self):
        db = dbc_lint.parse(DBC)
        self.assertEqual(len(db.messages), 7)
        self.assertEqual(db.cycle_ms[256], 100)
        self.assertEqual(db.values[(256, "State")][3], "FAULT")

    def test_each_rule_fires(self):
        cases = {
            "D01": DBC.replace("BO_ 257 BMS_CellV", "BO_ 256 BMS_CellV"),
            "D02": DBC.replace("SG_ Checksum : 16|8@1+", "SG_ Checksum : 20|8@1+"),
            "D03": DBC.replace("SG_ Cell2 : 16|16@1+", "SG_ Cell2 : 12|16@1+"),
            "D04": DBC.replace('SG_ SOC : 40|8@1+ (0.5,0) [0|100]', 'SG_ SOC : 40|8@1+ (0.5,0) [0|200]'),
            "D05": DBC.replace('BA_ "GenMsgCycleTime" BO_ 258 100;\n', ""),
            "D06": DBC.replace("SG_ Temp2 : 16|16@1-", "SG_ Temp2 : 16|16@0-"),
        }
        for code, text in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, errors(text))

    def test_header_drift_is_detected(self):
        moved_bit = HEADER.replace("BMS_FAULT_OT = 1u << 2", "BMS_FAULT_OT = 1u << 5")
        self.assertIn("D07", errors(header=moved_bit))
        renumbered = HEADER.replace("BMS_STATE_FAULT = 3", "BMS_STATE_FAULT = 4")
        self.assertIn("D07", errors(header=renumbered))


if __name__ == "__main__":
    unittest.main()
