import pytest
import json
import hashlib
import ast
from sil.harness import SILHarness, BMS_State
from sil.utils import verifies

def run_test(tc_id, duration_ms, faults=None):
    h = SILHarness(tc_id)
    if faults:
        for f in faults:
            h.inject(**f)
    h.run(duration_ms)
    h.save_trace()
    return h

def test_TC_QA_001_assertions():
    # Parse this file and check that every function starting with test_ has an assert
    with open(__file__, "r") as f:
        tree = ast.parse(f.read())
    
    no_asserts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            # skip itself to avoid false positive if we count the assert below?
            # actually this function has an assert below.
            has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(node))
            if not has_assert:
                no_asserts.append(node.name)
    assert not no_asserts, f"Tests missing assertions: {no_asserts}"

@verifies("SWR-012")
def test_TC_STAT_001():
    # INIT to STANDBY
    h = run_test("TC-STAT-001", 150)
    assert h.trace[-1]["state"] == 1 # STANDBY

@verifies("SWR-013")
def test_TC_STAT_002():
    # STANDBY to CLOSED
    h = SILHarness("TC-STAT-002")
    h.run(150)
    h.vcu_contactor_req = True
    h.run(60)
    h.save_trace()
    assert h.trace[-1]["state"] == 2 # CLOSED
    assert h.trace[-1]["contactor_close"] == True

@verifies("SWR-014")
def test_TC_STAT_003():
    # CLOSED to STANDBY
    h = SILHarness("TC-STAT-003")
    h.run(150)
    h.vcu_contactor_req = True
    h.run(100)
    h.vcu_contactor_req = False
    h.run(100)
    h.save_trace()
    assert h.trace[-1]["state"] == 1 # STANDBY
    assert h.trace[-1]["contactor_close"] == False

@verifies("SWR-004")
def test_TC_PROT_001():
    # OV threshold
    h = run_test("TC-PROT-001", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 0, "voltage": 4.26}])
    assert h.trace[-1]["state"] == 3 # FAULT
    assert (h.trace[-1]["faults"] & 0x01) != 0 # BMS_FAULT_OV

@verifies("SWR-005")
def test_TC_PROT_002():
    # UV threshold
    h = run_test("TC-PROT-002", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 1, "voltage": 2.7}])
    assert h.trace[-1]["state"] == 3 # FAULT
    assert (h.trace[-1]["faults"] & 0x02) != 0 # BMS_FAULT_UV

@verifies("SWR-006")
def test_TC_PROT_003():
    # UV debounce
    h = run_test("TC-PROT-003", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 1, "voltage": 2.7}])
    assert h.trace[-1]["state"] == 3
    # Check 3 samples delay
    fault_idx = next(i for i, t in enumerate(h.trace) if (t["faults"] & 0x02))
    assert 170 <= h.trace[fault_idx]["time_ms"] <= 190

@verifies("SWR-007")
def test_TC_PROT_004():
    h = run_test("TC-PROT-004", 200, [{"fault_type": "temperature_ramp", "at_ms": 0, "duration_ms": 200, "cell_idx": 1, "ramp_rate": 500.0}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x04) != 0

@verifies("SWR-008")
def test_TC_PROT_005():
    h = run_test("TC-PROT-005", 200, [
        {"fault_type": "current_step", "at_ms": 0, "duration_ms": 200, "current_a": -20.0},
        {"fault_type": "temperature_ramp", "at_ms": 0, "duration_ms": 200, "cell_idx": 0, "ramp_rate": -500.0}
    ])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x08) != 0

@verifies("SWR-009")
def test_TC_PROT_006():
    # OC
    h = run_test("TC-PROT-006", 200, [{"fault_type": "current_step", "at_ms": 150, "duration_ms": 50, "current_a": 160.0}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x10) != 0 # BMS_FAULT_OC

@verifies("SWR-010")
def test_TC_PROT_007():
    # Response time <= 100ms
    h = SILHarness("TC-PROT-007")
    h.run(150)
    h.vcu_contactor_req = True
    h.run(60)
    assert h.trace[-1]["contactor_close"] == True
    h.inject("current_step", at_ms=210, duration_ms=100, current_a=200.0)
    h.run(100)
    h.save_trace()
    assert h.trace[-1]["contactor_close"] == False

@verifies("SWR-015")
def test_TC_COMM_001():
    # Timeout
    h = SILHarness("TC-COMM-001")
    h.inject("can_loss", at_ms=0, duration_ms=350)
    h.run(350)
    h.save_trace()
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0 # BMS_FAULT_COMM

@verifies("SWR-015")
def test_TC_COMM_002():
    h = run_test("TC-COMM-002", 500, [{"fault_type": "can_loss", "at_ms": 100, "duration_ms": 400}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0

@verifies("SWR-015")
def test_TC_COMM_003():
    h = run_test("TC-COMM-003", 500, [{"fault_type": "can_delay", "at_ms": 100, "duration_ms": 400, "delay_ms": 350}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0

@verifies("SWR-016")
def test_TC_COMM_004():
    # Corrupt frames should be ignored (SWR-016)
    h = SILHarness("TC-COMM-004")
    h.inject("can_corrupt", at_ms=100, duration_ms=400)
    h.run(150)
    h.vcu_contactor_req = True
    h.run(100)
    assert h.trace[-1]["contactor_close"] == False
    assert h.trace[-1]["state"] in (1, 3)
    h.run(200)
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0

@verifies("SWR-030")
def test_TC_COMM_005():
    h = SILHarness("TC-COMM-005")
    h.run(150)
    h.vcu_contactor_req = True
    h.run(60)
    h.inject("current_step", at_ms=200, duration_ms=600, current_a=10.0)
    h.inject("can_loss", at_ms=200, duration_ms=600)
    h.run(350) # to 560ms
    h.save_trace()
    assert h.trace[-1]["state"] == 3
    assert h.trace[-1]["contactor_close"] == True
    
    h.inject("current_step", at_ms=560, duration_ms=200, current_a=4.0)
    h.run(20) # 2 samples
    assert h.trace[-1]["contactor_close"] == True
    h.run(10) # 3rd sample
    assert h.trace[-1]["contactor_close"] == False

def test_TC_COMM_006():
    # No-fault control test
    h = SILHarness("TC-COMM-006")
    h.run(1000)
    assert h.trace[-1]["state"] == 1 # STANDBY
    assert h.trace[-1]["faults"] == 0

@verifies("SWR-017")
def test_TC_MSG_001():
    h = SILHarness("TC-MSG-001")
    h.run(1000)
    tx_log = getattr(h, "can_tx_log", [])
    t_msg = [t for t, mid, _ in tx_log if mid == 256]
    assert len(t_msg) > 5
    periods = [t_msg[i] - t_msg[i-1] for i in range(1, len(t_msg))]
    assert all(p == 100 for p in periods)
    print(f"BMS_Status period: {periods[0]} ms")

@verifies("SWR-018")
def test_TC_MSG_002():
    h = SILHarness("TC-MSG-002")
    h.run(1000)
    tx_log = getattr(h, "can_tx_log", [])
    for msg_id, name in [(257, "BMS_CellV"), (258, "BMS_Temp")]:
        t_msg = [t for t, mid, _ in tx_log if mid == msg_id]
        assert len(t_msg) > 5
        periods = [t_msg[i] - t_msg[i-1] for i in range(1, len(t_msg))]
        assert all(p == 100 for p in periods)
        print(f"{name} period: {periods[0]} ms")

@verifies("SWR-019")
def test_TC_MSG_003():
    h = SILHarness("TC-MSG-003")
    h.inject("current_step", at_ms=212, duration_ms=200, current_a=200.0)
    h.run(500)
    fault_time = next((tr["time_ms"] for tr in h.trace if tr["state"] == 3), None)
    t_272 = [t for t, mid, _ in getattr(h, "can_tx_log", []) if mid == 272]
    assert len(t_272) > 0
    latency = t_272[0] - fault_time
    assert latency <= 10
    print(f"BMS_Fault latency: {latency} ms")

def test_TC_SYS_001():
    # Determinism
    h1 = run_test("TC-SYS-001-A", 200, [{"fault_type": "current_step", "at_ms": 100, "duration_ms": 50, "current_a": 10.0}])
    h2 = run_test("TC-SYS-001-B", 200, [{"fault_type": "current_step", "at_ms": 100, "duration_ms": 50, "current_a": 10.0}])
    
    with open(h1.evidence_dir / "trace.json", "rb") as f:
        hash1 = hashlib.md5(f.read()).hexdigest()
    with open(h2.evidence_dir / "trace.json", "rb") as f:
        hash2 = hashlib.md5(f.read()).hexdigest()
        
    assert hash1 == hash2
    print(f"Determinism proof: TC-SYS-001 {hash1} vs {hash2}")

@verifies("SWR-004")
def test_TC_PROT_008():
    h = run_test("TC-PROT-008", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 1, "voltage": 4.3}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x01) != 0

@verifies("SWR-004")
def test_TC_PROT_009():
    h = run_test("TC-PROT-009", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 2, "voltage": 4.3}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x01) != 0

@verifies("SWR-004")
def test_TC_PROT_010():
    h = run_test("TC-PROT-010", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 3, "voltage": 4.3}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x01) != 0

@verifies("SWR-005")
def test_TC_PROT_011():
    h = run_test("TC-PROT-011", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 0, "voltage": 2.7}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x02) != 0

@verifies("SWR-005")
def test_TC_PROT_012():
    h = run_test("TC-PROT-012", 200, [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 2, "voltage": 2.7}])
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x02) != 0

import ctypes
def test_struct_layout():
    fields = [f[0] for f in BMS_State._fields_]
    c_code = '#include <stdio.h>\n#include <stddef.h>\n#include "bms.h"\nint main() {\n'
    c_code += '    printf("size:%zu\\n", sizeof(bms_t));\n'
    for f in fields:
        c_code += f'    printf("{f}:%zu\\n", offsetof(bms_t, {f}));\n'
    c_code += '    return 0;\n}\n'
    import tempfile, subprocess, os
    with tempfile.TemporaryDirectory() as tmpdir:
        c_file = os.path.join(tmpdir, "check.c")
        exe = os.path.join(tmpdir, "check")
        with open(c_file, "w") as f:
            f.write(c_code)
        bms_h_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../firmware/include"))
        subprocess.run(["gcc", "-I", bms_h_dir, c_file, "-o", exe], check=True)
        out = subprocess.check_output([exe], text=True)
    c_offsets = {}
    for line in out.strip().split('\n'):
        k, v = line.split(':')
        c_offsets[k] = int(v)
    assert c_offsets["size"] == ctypes.sizeof(BMS_State), f"Size mismatch: C={c_offsets['size']} Py={ctypes.sizeof(BMS_State)}"
    for f in fields:
        py_offset = getattr(BMS_State, f).offset
        assert c_offsets[f] == py_offset, f"Offset mismatch for {f}: C={c_offsets[f]} Py={py_offset}"
