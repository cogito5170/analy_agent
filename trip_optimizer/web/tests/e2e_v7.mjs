import { chromium } from 'playwright';
import assert from 'node:assert';

(async () => {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    
    const SITE_URL = process.env.SITE_URL || 'http://localhost:8080/';
    
    console.log("Navigating to", SITE_URL);
    await page.goto(SITE_URL);
    
    // example data
    await page.click('#btnExample');
    await page.click('#btnOptimize');
    
    // wait for results
    await page.waitForSelector('.plan h4', { timeout: 10000 });
    
    const top1Text = await page.textContent('.plan:nth-child(1) h4');
    console.log("Top 1 before share:", top1Text);
    
    // Get the hash URL
    const shareUrl = await page.evaluate(() => window.location.href);
    console.log("Share URL:", shareUrl);
    
    // Open in new page
    const page2 = await context.newPage();
    await page2.goto(shareUrl);
    
    // It should automatically parse hash and optimize
    await page2.waitForSelector('.plan h4', { timeout: 10000 });
    
    const top1Text2 = await page2.textContent('.plan:nth-child(1) h4');
    console.log("Top 1 after share:", top1Text2);
    
    if (top1Text !== top1Text2) {
        console.error(`Mismatch: ${top1Text} vs ${top1Text2}`);
        process.exit(1);
    }
    
    console.log("V7 test passed");
    await browser.close();
})();
