with open('.github/workflows/engine.yml', 'r') as f:
    ci = f.read()

ci = ci.replace('node trip_optimizer/web/tests/error_test.mjs', 'node trip_optimizer/web/tests/error_test.mjs\n          node trip_optimizer/web/tests/e2e_v7.mjs')

with open('.github/workflows/engine.yml', 'w') as f:
    f.write(ci)
