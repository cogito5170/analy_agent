import pytest
import os
import subprocess
from pathlib import Path

def pytest_configure(config):
    config.addinivalue_line("markers", "verifies(req_id): mark test as verifying a requirement")
    
    # Build the shared library before tests
    sil_dir = Path(__file__).parent
    subprocess.run(["make", "-C", str(sil_dir)], check=True)

