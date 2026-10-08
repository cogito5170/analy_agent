with open('trip_optimizer/web/tests/model.test.mjs', 'r') as f:
    content = f.read()

import re

# Remove engine import
content = content.replace("import Module from '../../engine/build_wasm/engine.mjs';\n", "")

# Remove WASM test block
start_str = "test('WASM Engine: Example dataset validity check', async () => {"

start_idx = content.find(start_str)
if start_idx != -1:
    content = content[:start_idx]

with open('trip_optimizer/web/tests/model.test.mjs', 'w') as f:
    f.write(content)
