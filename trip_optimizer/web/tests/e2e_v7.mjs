import { chromium } from 'playwright';
import assert from 'node:assert';

async function runOptimization(page, costPerHour) {
    await page.fill('#costPerHour', costPerHour.toString());
    await page.click('#btnOptimize');
    await page.waitForSelector('.plan h4', { timeout: 10000 });
}

(async () => {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    
    const SITE_URL = process.env.SITE_URL || 'http://localhost:8080/';
    
    console.log("Navigating to", SITE_URL);
    await page.goto(SITE_URL);
    
    await page.click('#btnExample');

    async function verifyPlans(plans) {
        for (let i = 0; i < plans.length; i++) {
            const h4Text = await plans[i].textContent('.plan-heading');
            // Actually wait, let's just use textContent() on the element itself, since the h4 is a child or it is the element?
            const planEl = plans[i];
            const h4El = await planEl.$('h4');
            const h4TextFull = await h4El.textContent();
            
            const totalMatch = h4TextFull.match(/Total Cost:\s*([\d\.]+)/);
            const totalValue = totalMatch ? parseFloat(totalMatch[1]) : 0;

            const uls = await planEl.$$('ul');
            const costLi = await uls[0].$$('li');
            let transport = 0, lodging = 0, timeValue = 0, sum = 0;
            for (const li of costLi) {
                const text = await li.textContent();
                if (text.startsWith('Transport:')) transport = parseFloat(text.split(':')[1].trim());
                if (text.startsWith('Lodging:')) lodging = parseFloat(text.split(':')[1].trim());
                if (text.startsWith('Time Value:')) timeValue = parseFloat(text.split(':')[1].split('(')[0].trim());
                if (text.startsWith('Sum:')) sum = parseFloat(text.split(':')[1].trim());
            }

            const bookLi = await uls[2].$$('li');
            let legSum = 0, staySum = 0;
            for (const li of bookLi) {
                const text = await li.textContent();
                const match = text.match(/: ([\d\.]+) won/);
                if (!match) continue;
                const val = parseFloat(match[1]);
                if (text.includes('[Leg]')) legSum += val;
                if (text.includes('[Stay]')) staySum += val;
            }

            assert.strictEqual(transport, legSum, `Plan ${i+1}: transport breakdown mismatch`);
            assert.strictEqual(lodging, staySum, `Plan ${i+1}: lodging breakdown mismatch`);
            assert.strictEqual(transport + lodging + timeValue, sum, `Plan ${i+1}: sum breakdown mismatch`);
            assert.strictEqual(sum, totalValue, `Plan ${i+1}: breakdown sum (${sum}) != heading total (${totalValue})`);
        }
    }

    // Run with 0
    await runOptimization(page, 0);
    const plans0 = await page.$$('.plan');
    await verifyPlans(plans0);
    const top1Text0 = await page.textContent('.plan:nth-child(1) h4');
    console.log("Top 1 with cost 0:", top1Text0);

    // Run with 10000
    await runOptimization(page, 10000);
    const plans10000 = await page.$$('.plan');
    await verifyPlans(plans10000);
    console.log("Top 1 with cost 10000:", await page.textContent('.plan:nth-child(1) h4'));

    // Run with 12000
    await runOptimization(page, 12000);
    const plans12000 = await page.$$('.plan');
    await verifyPlans(plans12000);
    
    const top1Text12000 = await page.textContent('.plan:nth-child(1) h4');
    console.log("Top 1 with cost 12000:", top1Text12000);

    if (top1Text0 === top1Text12000) {
        throw new Error("Top 1 plan is identical despite value mode change (cost 0 vs 12000)");
    } else {
        console.log("Value mode difference confirmed.");
    }
    
    // Share link test
    const shareUrl = await page.evaluate(() => window.location.href);
    console.log("Share URL:", shareUrl);
    
    const page2 = await context.newPage();
    await page2.goto(shareUrl);
    
    await page2.waitForSelector('.plan h4', { timeout: 10000 });
    
    const top1Text2 = await page2.textContent('.plan:nth-child(1) h4');
    console.log("Top 1 after share:", top1Text2);
    
    if (top1Text12000 !== top1Text2) {
        throw new Error(`Mismatch: ${top1Text12000} vs ${top1Text2}`);
    }
    
    console.log("V7 test passed");
    await browser.close();
})();
