import sys

with open('trip_optimizer/engine/tests/v4_check.mjs', 'r') as f:
    content = f.read()

content = content.replace(
    "const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'v4_reference.json'), 'utf8'));",
    """const refPath = path.join(__dirname, 'v4_reference.json');
    if (!fs.existsSync(refPath)) {
        console.error('Reference file missing');
        process.exit(1);
    }
    const content = fs.readFileSync(refPath, 'utf8');
    if (!content.trim()) {
        console.error('Reference file empty');
        process.exit(1);
    }
    const data = JSON.parse(content);
    if (!Array.isArray(data) || data.length === 0) {
        console.error('Reference has zero problems');
        process.exit(1);
    }"""
)

content = content.replace(
    "let problems = 0;\n    let mismatches = 0;",
    "let problems = 0;\n    let mismatches = 0;\n    const counts = { '-2': 0, '-1': 0, '0': 0, 'plans': 0 };"
)

content = content.replace(
    "if (mismatch) mismatches++;",
    """if (mismatch) mismatches++;
        if (n === -2) counts['-2']++;
        else if (n === -1) counts['-1']++;
        else if (n === 0) counts['0']++;
        else if (n > 0) counts['plans']++;"""
)

content = content.replace(
    "console.log(`V4 result: ${problems} problems, ${mismatches} mismatches`);",
    "console.log(`V4 result: ${problems} problems, ${mismatches} mismatches, -2: ${counts['-2']}, -1: ${counts['-1']}, 0: ${counts['0']}, plans: ${counts['plans']}`);"
)

with open('trip_optimizer/engine/tests/v4_check.mjs', 'w') as f:
    f.write(content)
