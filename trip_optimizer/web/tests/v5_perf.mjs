import { chromium } from 'playwright';
import fs from 'fs';

(async () => {
    let nativeBudget = Infinity;
    let webBudget = Infinity;
    try {
        const perfMd = fs.readFileSync('trip_optimizer/docs/perf.md', 'utf8');
        const nativeMatch = perfMd.match(/Native Budget: ([\d.]+) ms/);
        const webMatch = perfMd.match(/Web Budget: ([\d.]+) ms/);
        if (nativeMatch) nativeBudget = parseFloat(nativeMatch[1]);
        if (webMatch) webBudget = parseFloat(webMatch[1]);
    } catch (e) {
        // file might not exist or be empty
    }

    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    const siteUrl = process.env.SITE_URL || `file://${process.cwd()}/../../site/index.html`;
    await page.goto(siteUrl);

    const problemRaw = fs.readFileSync('trip_optimizer/engine/build/v5_problem.json', 'utf8');
    const raw = JSON.parse(problemRaw);
    const problem = {
        priceArr: raw.price,
        minsArr: raw.minutes,
        lodgingArr: raw.lodging,
        stayMinArr: raw.stay_min,
        stayMaxArr: raw.stay_max,
        V: raw.visits,
        days: raw.days,
        M: raw.modes,
        departMin: raw.depart_min,
        departMax: raw.depart_max,
        costPerMinute: raw.cost_per_minute,
        k: raw.k
    };

    const times = await page.evaluate(async (prob) => {
        return new Promise((resolve, reject) => {
            const worker = new Worker('worker.mjs', { type: 'module' });
            let runs = 0;
            const runTimes = [];
            let start;
            worker.postMessage({ type: 'init' });
            worker.onmessage = (e) => {
                if (e.data.type === 'ready') {
                    start = performance.now();
                    worker.postMessage({ type: 'optimize', payload: prob });
                    return;
                }
                
                if (e.data.type === 'error') {
                    reject(e.data.error || e.data.payload || "Unknown error");
                    return;
                }

                if (e.data.type === 'success') {
                    const elapsed = performance.now() - start;
                    if (runs > 0) {
                        runTimes.push(elapsed);
                    }
                    runs++;
                    if (runs <= 5) {
                        start = performance.now();
                        worker.postMessage({ type: 'optimize', payload: prob });
                    } else {
                        worker.terminate();
                        resolve(runTimes);
                    }
                }
            };
        });
    }, problem);

    times.sort((a, b) => a - b);
    const medianWeb = times[2];
    console.log(`Web V5 median time: ${medianWeb.toFixed(2)} ms`);
    if (webBudget !== Infinity) {
        console.log(`Web Budget: ${webBudget} ms`);
        if (medianWeb > webBudget) {
            console.error(`Web performance exceeded budget! (${medianWeb.toFixed(2)} > ${webBudget})`);
            process.exit(1);
        }
    }
    await browser.close();
})();
