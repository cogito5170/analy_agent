import yaml

with open('.github/workflows/engine.yml', 'r') as f:
    content = f.read()

content = content.replace(
    "node --test tests/model.test.mjs",
    "node --test tests/model.test.mjs\n          node --test tests/wasm.test.mjs"
)

smoke_test_block = """
      - name: Install Playwright and server
        run: |
          npm init -y
          npm install playwright@1.47.2 http-server
          npx playwright install --with-deps chromium
          
      - name: Run Smoke Test
        run: |
          npx http-server site -p 8080 &
          sleep 3
          export SITE_URL=http://localhost:8080/
          node trip_optimizer/web/tests/smoke.mjs
          
      - name: Upload Screenshot
        uses: actions/upload-artifact@v7
        with:
          name: smoke-screenshot
          path: smoke-screenshot.png
          retention-days: 1
"""

# insert before Upload Static Site
content = content.replace("      - name: Upload Static Site", smoke_test_block.lstrip() + "      - name: Upload Static Site")

with open('.github/workflows/engine.yml', 'w') as f:
    f.write(content)
