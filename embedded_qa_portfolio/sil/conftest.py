import pytest
import os
import subprocess
from pathlib import Path
subprocess.run(["make", "-C", str(Path(__file__).parent)], check=True)
from sil.harness import SILHarness

def pytest_configure(config):
    config.addinivalue_line("markers", "verifies(req_id): mark test as verifying a requirement")
    config.addinivalue_line("markers", "technique(name): boundary_value, state_transition, fault_injection, timeout")
    

class SilRig:
    def __init__(self, request):
        self.tc_id = request.node.name
        # extract TC ID from test name if possible or just use test name
        self.harness = SILHarness(self.tc_id)
        
    def inject(self, fault_type, at_ms, duration_ms, **kwargs):
        self.harness.inject(fault_type, at_ms, duration_ms, **kwargs)
        
    def run(self, duration_ms):
        self.harness.run(duration_ms)
        
    def save_trace(self):
        self.harness.save_trace()
        
    @property
    def trace(self):
        return self.harness.trace
        
    @property
    def can_tx_log(self):
        return getattr(self.harness, "can_tx_log", [])
        
    @property
    def evidence_dir(self):
        return self.harness.evidence_dir
        
    @property
    def vcu_contactor_req(self):
        return self.harness.vcu_contactor_req

    @vcu_contactor_req.setter
    def vcu_contactor_req(self, value):
        self.harness.vcu_contactor_req = value

    def set_vcu_contactor_req(self, value):
        self.harness.vcu_contactor_req = value

class HwRig:
    def __init__(self):
        pytest.skip("HW rig is a stub and currently skips.")

@pytest.fixture
def rig(request):
    rig_type = request.config.getoption("--rig", default="sil")
    if rig_type == "sil":
        r = SilRig(request)
        yield r
        r.save_trace()
    else:
        yield HwRig()

def pytest_addoption(parser):
    parser.addoption("--rig", action="store", default="sil", help="Rig to use: sil or hw")
