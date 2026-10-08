import { chromium } from 'playwright';

(async () => {
    let hasError = false;
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    
    page.on('console', msg => {
        if (msg.type() === 'error') {
            console.error('Browser console error:', msg.text());
            hasError = true;
        }
    });
    
    page.on('pageerror', err => {
        console.error('Browser page error:', err);
        hasError = true;
    });

    // We assume this is run from the root of the site, or we pass URL
    // Actually we can just load the site locally via file://
    const siteUrl = process.env.SITE_URL || `file://${process.cwd()}/site/index.html`;
    await page.goto(siteUrl);
    
    // Use example dataset
    await page.click('#btnExample');
    
    // Optimize
    await page.click('#btnOptimize');
    
    // Wait for 5 plans
    await page.waitForSelector('text=Found 5 plans', { timeout: 10000 });
    
    // Check no console error
    if (hasError) {
        console.error("Smoke test failed: console errors detected");
        process.exit(1);
    }
    
    // Save screenshot
    await page.screenshot({ path: 'smoke-screenshot.png' });
    
    console.log("SMOKE TEST PASSED");
    await browser.close();
})();
