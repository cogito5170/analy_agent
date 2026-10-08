import re

with open('.github/workflows/engine.yml', 'r') as f:
    content = f.read()

# Pin http-server
content = content.replace('npm install playwright@1.47.2 http-server', 'npm install playwright@1.47.2 http-server@14.1.1')

# Add deploy job
deploy_job = """
  deploy:
    runs-on: ubuntu-latest
    needs: web
    if: github.ref == 'refs/heads/main'
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    permissions:
      pages: write
      id-token: write
    steps:
      - uses: actions/checkout@v7
      
      - name: Download Static Site
        uses: actions/download-artifact@v8
        with:
          name: site
          path: site
          
      - name: Upload Pages Artifact
        uses: actions/upload-pages-artifact@v4
        with:
          path: site
          
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
        
      - name: Install Playwright
        run: |
          npm init -y
          npm install playwright@1.47.2
          npx playwright install --with-deps chromium
          
      - name: Run Smoke Test Against Deployed URL
        run: |
          export SITE_URL="${{ steps.deployment.outputs.page_url }}"
          node trip_optimizer/web/tests/smoke.mjs
"""

content += deploy_job

with open('.github/workflows/engine.yml', 'w') as f:
    f.write(content)

