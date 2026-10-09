import xml.etree.ElementTree as ET
import sys
from pathlib import Path

def main():
    if not Path("report.xml").exists():
        print("report.xml not found")
        sys.exit(1)
        
    tree = ET.parse("report.xml")
    root = tree.getroot()
    
    # We might have testsuites -> testsuite
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    else:
        suites = [root]
        
    md = ["# SIL Test Report\n"]
    
    total_tests = 0
    failures = 0
    time = 0.0
    
    for suite in suites:
        total_tests += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        time += float(suite.get("time", 0.0))
        
    md.append(f"**Total Tests**: {total_tests}")
    md.append(f"**Failures**: {failures}")
    md.append(f"**Time**: {time:.2f} s\n")
    
    if failures > 0:
        md.append("## Failing Tests\n")
        for suite in suites:
            for case in suite.findall("testcase"):
                fail = case.find("failure")
                err = case.find("error")
                if fail is not None or err is not None:
                    name = case.get("name")
                    classname = case.get("classname")
                    file = case.get("file", "sil/test_sil.py")
                    
                    # Extract TC ID
                    tc_id = name
                    # Evidence path is usually evidence/TC_ID
                    evidence = f"sil/evidence/{tc_id}"
                    
                    md.append(f"### `{name}`")
                    md.append(f"- **Reproduce**: `pytest {file}::{name}`")
                    md.append(f"- **Evidence path**: `{evidence}`")
                    
                    msg = fail.get("message") if fail is not None else err.get("message")
                    md.append("```\n" + str(msg) + "\n```\n")
                    
    with open("sil_report.md", "w") as f:
        f.write("\n".join(md))

    # We must print the summary for the dispatcher!
    print(f"SIL run complete: {total_tests} tests, {total_tests - failures} passed, time {time:.2f} s")
    
if __name__ == "__main__":
    main()
