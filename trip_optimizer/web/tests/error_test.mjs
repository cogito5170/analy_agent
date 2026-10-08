import { chromium } from 'playwright';

(async () => {
    const browser = await chromium.launch({ headless: true });
    
    // Test 1: Engine Error (Empty Visit List)
    console.log("Running Test 1: Engine error");
    const page1 = await browser.newPage();
    const siteUrl = process.env.SITE_URL || `file://${process.cwd()}/../../site/index.html`;
    await page1.goto(siteUrl);
    await page1.click('#btnExample');
    await page1.fill('#visitLines', ''); 
    await page1.fill('#transportLines', ''); 
    await page1.fill('#lodgingLines', '');
    await page1.click('#btnOptimize');
    await page1.waitForSelector('.error', { timeout: 10000 });
    const statusText1 = await page1.innerText('#status');
    console.log("Engine error message shown:", statusText1);
    if (!statusText1.includes('visits must be')) {
        console.error("Test 1 Failed");
        process.exit(1);
    }
    await page1.close();
    
    // Test 2: onerror (engine.mjs fails to load)
    console.log("Running Test 2: onerror (engine.mjs fails)");
    const page2 = await browser.newPage();
    await page2.route('**/engine.mjs', route => route.abort('failed'));
    await page2.goto(siteUrl);
    await page2.waitForSelector('.error', { timeout: 10000 });
    const statusText2 = await page2.innerText('#status');
    console.log("onerror message shown:", statusText2);
    if (!statusText2.includes('failed')) {
        console.error("Test 2 Failed");
        process.exit(1);
    }
    await page2.close();

    // Test 3: init 'error' message path (Module() rejects because engine.wasm fails)
    console.log("Running Test 3: init error (Module rejects)");
    const page3 = await browser.newPage();
    await page3.route('**/engine.wasm', route => route.abort('failed'));
    await page3.goto(siteUrl);
    await page3.waitForSelector('.error', { timeout: 10000 });
    const statusText3 = await page3.innerText('#status');
    console.log("init error message shown:", statusText3);
    if (!statusText3.toLowerCase().includes('failed') && !statusText3.includes('Error')) {
        console.error("Test 3 Failed");
        process.exit(1);
    }
    await page3.close();

    // Test 4: negative or non-numeric hour values
    console.log("Running Test 4: hour value validation");
    const page4 = await browser.newPage();
    await page4.goto(siteUrl);
    await page4.click('#btnExample');
    
    // Test non-numeric
    await page4.evaluate(() => document.getElementById('costPerHour').value = 'abc');
    await page4.click('#btnOptimize');
    let cphError = await page4.innerText('#costPerHourError');
    if (!cphError.includes('must be a non-negative number')) {
        console.error("Test 4 Failed on non-numeric. Message:", cphError);
        process.exit(1);
    }

    // Test negative
    await page4.fill('#costPerHour', '-10');
    await page4.click('#btnOptimize');
    cphError = await page4.innerText('#costPerHourError');
    if (!cphError.includes('must be a non-negative number')) {
        console.error("Test 4 Failed on negative. Message:", cphError);
        process.exit(1);
    }
    await page4.close();
    
    console.log("ERROR TESTS PASSED");
    await browser.close();
})();
