import yaml
import re
import sys
from pathlib import Path

def main():
    repo_root = Path(__file__).resolve().parent.parent
    swr_path = repo_root / "requirements" / "swr.yaml"
    
    with open(swr_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    requirements = data.get("requirements", [])
    
    # Extract @verifies tags from test files
    test_files = list((repo_root / "sil").rglob("test_*.py"))
    
    linked = {} # SWR -> list of tests
    
    for tf in test_files:
        content = tf.read_text(encoding="utf-8")
        # Match @verifies("SWR-XXX")\ndef test_name(...)
        matches = re.finditer(r'@verifies\("([^"]+)"\)\n(?:@[^\n]+\n)*def (test_[A-Z0-9_]+)\(', content)
        for m in matches:
            swr_id = m.group(1)
            test_name = m.group(2)
            if swr_id not in linked:
                linked[swr_id] = []
            linked[swr_id].append(test_name)
            
    total_swrs = len(requirements)
    test_method_swrs = [req for req in requirements if req.get("method") == "test"]
    num_test_swrs = len(test_method_swrs)
    
    linked_test_swrs = 0
    missing = []
    
    matrix_lines = ["| Requirement ID | Requirement Text | Method | Linked Tests |", "| --- | --- | --- | --- |"]
    
    for req in requirements:
        swr_id = req["id"]
        method = req.get("method", "")
        text = req.get("text", "").replace("\n", " ")
        tests = ", ".join(linked.get(swr_id, []))
        
        if method == "test":
            if tests:
                linked_test_swrs += 1
            else:
                missing.append(swr_id)
                
        matrix_lines.append(f"| {swr_id} | {text} | {method} | {tests} |")
        
    with open(repo_root / "traceability_matrix.md", "w", encoding="utf-8") as f:
        f.write("\n".join(matrix_lines))
        
    unique_tcs = set(sum(linked.values(), []))
    print(f"Requirement TCs: {len(unique_tcs)}")
    print(f"Total SWRs: {total_swrs}")
    print(f"Test-method SWRs: {num_test_swrs}")
    print(f"Linked test-method SWRs: {linked_test_swrs}")
    
    if missing:
        print(f"Missing tests for: {', '.join(missing)}")
        sys.exit(1)
    else:
        print("All test-method SWRs are linked.")
        sys.exit(0)

if __name__ == "__main__":
    main()
