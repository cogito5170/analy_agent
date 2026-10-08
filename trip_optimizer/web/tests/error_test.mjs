import { chromium } from 'playwright';

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    
    let pendingErrors = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            pendingErrors.push(msg.text());
        }
    });
    page.on('pageerror', err => {
        pendingErrors.push(err.toString());
    });

    const siteUrl = process.env.SITE_URL || `file://${process.cwd()}/site/index.html`;
    
    // Test 1: Engine Error (Empty Visit List)
    console.log("Running Test 1: Engine error");
    await page.goto(siteUrl);
    await page.click('#btnExample');
    await page.fill('#visitLines', ''); // Empty visit list
    await page.fill('#transportLines', ''); // Clear to avoid parse errors
    await page.fill('#lodgingLines', '');
    await page.click('#btnOptimize');
    // It should leave the Optimizing state and show an error in #status
    await page.waitForSelector('.error', { timeout: 10000 });
    const statusText1 = await page.innerText('#status');
    console.log("Engine error message shown:", statusText1);
    if (!statusText1.includes('visits must be')) {
        console.error("Test 1 Failed: error message not found in status");
        process.exit(1);
    }
    
    // Test 2: Module load failure
    // We can simulate this by intercepting the WASM file or engine.mjs
    console.log("Running Test 2: Module load failure");
    await page.route('**/engine.wasm', route => route.abort('failed'));
    await page.route('**/engine.mjs', route => route.abort('failed'));
    await page.goto(siteUrl);
    
    // Assert error visible without pressing optimize
    await page.waitForSelector('.error', { timeout: 10000 });
    const statusText2Pre = await page.innerText('#status');
    console.log("Load failure message shown without Optimize:", statusText2Pre);
    if (!statusText2Pre.includes('Error') && !statusText2Pre.includes('failed')) {
        console.error("Test 2 Failed: module load error message not found in status without optimize");
        process.exit(1);
    }
    
    await page.click('#btnExample');
    await page.click('#btnOptimize');
    await page.waitForSelector('.error', { timeout: 10000 });
    const statusText2 = await page.innerText('#status');
    console.log("Load failure message shown:", statusText2);
    if (!statusText2.includes('Error') && !statusText2.includes('failed')) {
        console.error("Test 2 Failed: module load error message not found in status");
        process.exit(1);
    }
    
    console.log("ERROR TESTS PASSED");
    await browser.close();
})();
