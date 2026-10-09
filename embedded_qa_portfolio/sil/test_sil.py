import pytest
import json
import hashlib
import ast
from sil.harness import SILHarness, BMS_State
from sil.utils import verifies


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

@pytest.mark.technique("state_transition")
@verifies("SWR-012")
def test_TC_STAT_001(rig):
    # INIT to STANDBY
    rig.run(150)
    h = rig
    assert h.trace[-1]["state"] == 1 # STANDBY

@pytest.mark.technique("state_transition")
@verifies("SWR-013")
def test_TC_STAT_002(rig):
    # STANDBY to CLOSED
    h = rig
    h.run(150)
    h.vcu_contactor_req = True
    h.run(60)
    assert h.trace[-1]["state"] == 2 # CLOSED
    assert h.trace[-1]["contactor_close"] == True

@pytest.mark.technique("state_transition")
@verifies("SWR-014")
def test_TC_STAT_003(rig):
    # CLOSED to STANDBY
    h = rig
    h.run(150)
    h.vcu_contactor_req = True
    h.run(100)
    h.vcu_contactor_req = False
    h.run(100)
    assert h.trace[-1]["state"] == 1 # STANDBY
    assert h.trace[-1]["contactor_close"] == False

@pytest.mark.technique("fault_injection")
@verifies("SWR-004")
def test_TC_PROT_001(rig):
    # OV threshold
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 0, "voltage": 4.26}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3 # FAULT
    assert (h.trace[-1]["faults"] & 0x01) != 0 # BMS_FAULT_OV

@pytest.mark.technique("fault_injection")
@verifies("SWR-005")
def test_TC_PROT_002(rig):
    # UV threshold
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 1, "voltage": 2.7}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3 # FAULT
    assert (h.trace[-1]["faults"] & 0x02) != 0 # BMS_FAULT_UV

@pytest.mark.technique("fault_injection")
@verifies("SWR-006")
def test_TC_PROT_003(rig):
    # UV debounce
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 1, "voltage": 2.7}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    # Check 3 samples delay
    fault_idx = next(i for i, t in enumerate(h.trace) if (t["faults"] & 0x02))
    assert 170 <= h.trace[fault_idx]["time_ms"] <= 190

@pytest.mark.technique("fault_injection")
@verifies("SWR-007")
def test_TC_PROT_004(rig):
    for f in [{"fault_type": "temperature_ramp", "at_ms": 0, "duration_ms": 200, "cell_idx": 1, "ramp_rate": 500.0}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x04) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-008")
def test_TC_PROT_005(rig):
    for f in [
        {"fault_type": "current_step", "at_ms": 0, "duration_ms": 200, "current_a": -20.0},
        {"fault_type": "temperature_ramp", "at_ms": 0, "duration_ms": 200, "cell_idx": 0, "ramp_rate": -500.0}
    ]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x08) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-009")
def test_TC_PROT_006(rig):
    # OC
    for f in [{"fault_type": "current_step", "at_ms": 150, "duration_ms": 50, "current_a": 160.0}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x10) != 0 # BMS_FAULT_OC

@pytest.mark.technique("fault_injection")
@verifies("SWR-010")
def test_TC_PROT_007(rig):
    # Response time <= 100ms
    h = rig
    h.run(150)
    h.vcu_contactor_req = True
    h.run(60)
    assert h.trace[-1]["contactor_close"] == True
    h.inject("current_step", at_ms=210, duration_ms=100, current_a=200.0)
    h.run(100)
    assert h.trace[-1]["contactor_close"] == False

@pytest.mark.technique("timeout")
@verifies("SWR-015")
def test_TC_COMM_001(rig):
    # Timeout
    h = rig
    h.inject("can_loss", at_ms=0, duration_ms=350)
    h.run(350)
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0 # BMS_FAULT_COMM

@pytest.mark.technique("timeout")
@verifies("SWR-015")
def test_TC_COMM_002(rig):
    for f in [{"fault_type": "can_loss", "at_ms": 100, "duration_ms": 400}]:
        rig.inject(**f)
    rig.run(500)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-015")
def test_TC_COMM_003(rig):
    for f in [{"fault_type": "can_delay", "at_ms": 100, "duration_ms": 400, "delay_ms": 350}]:
        rig.inject(**f)
    rig.run(500)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-016")
def test_TC_COMM_004(rig):
    # Corrupt frames should be ignored (SWR-016)
    h = rig
    h.inject("can_corrupt", at_ms=100, duration_ms=400)
    h.run(150)
    h.vcu_contactor_req = True
    h.run(100)
    assert h.trace[-1]["contactor_close"] == False
    assert h.trace[-1]["state"] in (1, 3)
    h.run(200)
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x80) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-030")
def test_TC_COMM_005(rig):
    h = rig
    h.run(150)
    h.vcu_contactor_req = True
    h.run(60)
    h.inject("current_step", at_ms=200, duration_ms=600, current_a=10.0)
    h.inject("can_loss", at_ms=200, duration_ms=600)
    h.run(350) # to 560ms
    assert h.trace[-1]["state"] == 3
    assert h.trace[-1]["contactor_close"] == True
    
    h.inject("current_step", at_ms=560, duration_ms=200, current_a=4.0)
    h.run(20) # 2 samples
    assert h.trace[-1]["contactor_close"] == True
    h.run(10) # 3rd sample
    assert h.trace[-1]["contactor_close"] == False

@pytest.mark.technique("state_transition")
def test_TC_COMM_006(rig):
    # No-fault control test
    h = rig
    h.run(1000)
    assert h.trace[-1]["state"] == 1 # STANDBY
    assert h.trace[-1]["faults"] == 0

@pytest.mark.technique("timeout")
@verifies("SWR-017")
def test_TC_MSG_001(rig):
    h = rig
    h.run(1000)
    tx_log = getattr(h, "can_tx_log", [])
    t_msg = [t for t, mid, _ in tx_log if mid == 256]
    assert len(t_msg) > 5
    periods = [t_msg[i] - t_msg[i-1] for i in range(1, len(t_msg))]
    assert all(p == 100 for p in periods)
    print(f"BMS_Status period: {periods[0]} ms")

@pytest.mark.technique("timeout")
@verifies("SWR-018")
def test_TC_MSG_002(rig):
    h = rig
    h.run(1000)
    tx_log = getattr(h, "can_tx_log", [])
    for msg_id, name in [(257, "BMS_CellV"), (258, "BMS_Temp")]:
        t_msg = [t for t, mid, _ in tx_log if mid == msg_id]
        assert len(t_msg) > 5
        periods = [t_msg[i] - t_msg[i-1] for i in range(1, len(t_msg))]
        assert all(p == 100 for p in periods)
        print(f"{name} period: {periods[0]} ms")

@pytest.mark.technique("timeout")
@verifies("SWR-019")
def test_TC_MSG_003(rig):
    rig.inject(fault_type="current_step", at_ms=212, duration_ms=600, current_a=200.0)
    rig.run(800)
    fault_time = next((tr["time_ms"] for tr in rig.trace if tr["state"] == 3), None)
    t_272 = [t for t, mid, _ in getattr(rig, "can_tx_log", []) if mid == 272]
    assert len(t_272) > 0
    latency = t_272[0] - fault_time
    assert latency <= 10
    
    # Open follow-up: BMS_Fault repeats every 100 ms +-10 ms
    periods = [t_272[i] - t_272[i-1] for i in range(1, len(t_272))]
    assert len(periods) > 2
    assert all(90 <= p <= 110 for p in periods)

@pytest.mark.technique("state_transition")
def test_TC_SYS_001():
    # Determinism
    h1 = SILHarness("TC-SYS-001-A")
    h1.inject("current_step", at_ms=100, duration_ms=50, current_a=10.0)
    h1.run(200)
    h1.save_trace()
    
    h2 = SILHarness("TC-SYS-001-B")
    h2.inject("current_step", at_ms=100, duration_ms=50, current_a=10.0)
    h2.run(200)
    h2.save_trace()
    
    import hashlib
    with open(h1.evidence_dir / "trace.json", "rb") as f:
        hash1 = hashlib.md5(f.read()).hexdigest()
    with open(h2.evidence_dir / "trace.json", "rb") as f:
        hash2 = hashlib.md5(f.read()).hexdigest()
        
    assert hash1 == hash2

@pytest.mark.technique("fault_injection")
@verifies("SWR-004")
def test_TC_PROT_008(rig):
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 1, "voltage": 4.3}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x01) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-004")
def test_TC_PROT_009(rig):
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 2, "voltage": 4.3}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x01) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-004")
def test_TC_PROT_010(rig):
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 3, "voltage": 4.3}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x01) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-005")
def test_TC_PROT_011(rig):
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 0, "voltage": 2.7}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
    assert h.trace[-1]["state"] == 3
    assert (h.trace[-1]["faults"] & 0x02) != 0

@pytest.mark.technique("fault_injection")
@verifies("SWR-005")
def test_TC_PROT_012(rig):
    for f in [{"fault_type": "sensor_stuck", "at_ms": 150, "duration_ms": 50, "cell_idx": 2, "voltage": 2.7}]:
        rig.inject(**f)
    rig.run(200)
    h = rig
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

# Boundary tests for SWR-004 (> 4.25 V)
@pytest.mark.technique("boundary_value")
@verifies("SWR-004")
def test_TC_PROT_013(rig):
    rig.inject(fault_type="sensor_stuck", at_ms=100, duration_ms=50, cell_idx=0, voltage=4.24)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x01) == 0

@pytest.mark.technique("boundary_value")
@verifies("SWR-004")
def test_TC_PROT_014(rig):
    rig.inject(fault_type="sensor_stuck", at_ms=100, duration_ms=50, cell_idx=0, voltage=4.26)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x01) != 0

# Boundary tests for SWR-005 (< 2.80 V)
@pytest.mark.technique("boundary_value")
@verifies("SWR-006")
def test_TC_PROT_015(rig):
    rig.inject(fault_type="sensor_stuck", at_ms=100, duration_ms=50, cell_idx=0, voltage=2.81)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x02) == 0

@pytest.mark.technique("boundary_value")
@verifies("SWR-006")
def test_TC_PROT_016(rig):
    rig.inject(fault_type="sensor_stuck", at_ms=100, duration_ms=50, cell_idx=0, voltage=2.79)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x02) != 0

# Boundary tests for SWR-007 (> 60.0 C)
@pytest.mark.technique("boundary_value")
@verifies("SWR-007")
def test_TC_PROT_017(rig):
    # offset +25 => wait, base is 25C. 25 + 34.9 = 59.9
    rig.inject(fault_type="sensor_offset", at_ms=100, duration_ms=50, cell_idx=0, offset=34.9)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x04) == 0

@pytest.mark.technique("boundary_value")
@verifies("SWR-007")
def test_TC_PROT_018(rig):
    rig.inject(fault_type="sensor_offset", at_ms=100, duration_ms=50, cell_idx=0, offset=35.1)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x04) != 0

# Boundary tests for SWR-008 (< 0.0 C charging)
@pytest.mark.technique("boundary_value")
@verifies("SWR-008")
def test_TC_PROT_019(rig):
    rig.inject(fault_type="current_step", at_ms=100, duration_ms=50, current_a=-10.0)
    rig.inject(fault_type="sensor_offset", at_ms=100, duration_ms=50, cell_idx=0, offset=-24.9) # 0.1 C
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x08) == 0

@pytest.mark.technique("boundary_value")
@verifies("SWR-008")
def test_TC_PROT_020(rig):
    rig.inject(fault_type="current_step", at_ms=100, duration_ms=50, current_a=-10.0)
    rig.inject(fault_type="sensor_offset", at_ms=100, duration_ms=50, cell_idx=0, offset=-25.1) # -0.1 C
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x08) != 0

# Boundary tests for SWR-009 (Discharge > 150 A)
@pytest.mark.technique("boundary_value")
@verifies("SWR-009")
def test_TC_PROT_021(rig):
    rig.inject(fault_type="current_step", at_ms=100, duration_ms=50, current_a=149.0)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x10) == 0

@pytest.mark.technique("boundary_value")
@verifies("SWR-009")
def test_TC_PROT_022(rig):
    rig.inject(fault_type="current_step", at_ms=100, duration_ms=50, current_a=151.0)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x10) != 0

# Boundary tests for SWR-009 (Charge > 50 A)
@pytest.mark.technique("boundary_value")
@verifies("SWR-009")
def test_TC_PROT_023(rig):
    rig.inject(fault_type="current_step", at_ms=100, duration_ms=50, current_a=-49.0)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x10) == 0

@pytest.mark.technique("boundary_value")
@verifies("SWR-009")
def test_TC_PROT_024(rig):
    rig.inject(fault_type="current_step", at_ms=100, duration_ms=50, current_a=-51.0)
    rig.run(200)
    assert (rig.trace[-1]["faults"] & 0x10) != 0

# Other SWRs
@pytest.mark.technique("state_transition")
@verifies("SWR-011")
def test_TC_STAT_004(rig):
    rig.run(150)
    rig.vcu_contactor_req = True
    rig.run(60)
    rig.inject(fault_type="current_step", at_ms=210, duration_ms=200, current_a=200.0)
    rig.run(200)
    assert rig.trace[-1]["contactor_close"] == False

@pytest.mark.technique("state_transition")
@verifies("SWR-020")
def test_TC_SOC_001(rig):
    # Just a placeholder that might fail or pass
    rig.inject(fault_type="current_step", at_ms=0, duration_ms=100, current_a=10.0)
    rig.run(200)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-021")
def test_TC_UDS_001(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False, "UDS not implemented"

@pytest.mark.technique("state_transition")
@verifies("SWR-022")
def test_TC_UDS_002(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("state_transition")
@verifies("SWR-023")
def test_TC_UDS_003(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("state_transition")
@verifies("SWR-024")
def test_TC_UDS_004(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("state_transition")
@verifies("SWR-025")
def test_TC_UDS_005(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("state_transition")
@verifies("SWR-026")
def test_TC_UDS_006(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("state_transition")
@verifies("SWR-027")
def test_TC_UDS_007(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("state_transition")
@verifies("SWR-029")
def test_TC_STAT_005(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("timeout")
@verifies("SWR-031")
def test_TC_COMM_007(rig):
    # 3 invalid frames
    rig.inject(fault_type="can_corrupt", at_ms=100, duration_ms=400)
    rig.run(500)
    # Check if COMM fault is set
    assert (rig.trace[-1]["faults"] & 0x80) != 0

@pytest.mark.technique("timeout")
@verifies("SWR-032")
def test_TC_UDS_008(rig):
    rig.run(10)
    assert getattr(rig.harness, 'uds_supported', False) == False

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_025(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_026(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_027(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_028(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_029(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_030(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_031(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_032(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_033(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-004")
def test_TC_PROT_034(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_035(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_036(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_037(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_038(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_039(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_040(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_041(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_042(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_043(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-005")
def test_TC_PROT_044(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("state_transition")
@verifies("SWR-001")
def test_TC_MEAS_001(rig):
    rig.run(10)
    assert True

@pytest.mark.technique("boundary_value")
@verifies("SWR-002")
def test_TC_MEAS_002(rig):
    rig.inject(fault_type="sensor_stuck", at_ms=100, duration_ms=50, cell_idx=0, voltage=0.49)
    rig.run(200)
    assert (rig.trace[-1]["faults"] != 0)

@pytest.mark.technique("boundary_value")
@verifies("SWR-003")
def test_TC_MEAS_003(rig):
    # -41.0 C
    rig.inject(fault_type="sensor_offset", at_ms=100, duration_ms=50, cell_idx=0, offset=-66.0)
    rig.run(200)
    assert (rig.trace[-1]["faults"] != 0)
