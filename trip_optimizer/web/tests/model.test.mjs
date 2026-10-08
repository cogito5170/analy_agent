import test from 'node:test';
import assert from 'node:assert';
import { parseData, decodePlans } from '../model.mjs';
import Module from '../../engine/build_wasm/engine.mjs';

test('parseData: CSV parsing and error line numbers', () => {
    // Unknown city on transport
    assert.throws(() => {
        parseData({
            startCity: 'Seoul', endCity: 'Seoul',
            visitLines: 'Tokyo,1,2',
            transportLines: 'Seoul,Busan,2027-04-01,Bus,10,10',
            lodgingLines: '',
            startDate: '2027-04-01', days: 5, costPerMinute: 0, k: 1
        });
    }, /Unknown city 'Busan' on transport line 1/);

    // Unknown city on lodging
    assert.throws(() => {
        parseData({
            startCity: 'Seoul', endCity: 'Seoul',
            visitLines: 'Tokyo,1,2',
            transportLines: 'Seoul,Tokyo,2027-04-01,Flight,10,10',
            lodgingLines: 'Kyoto,2027-04-01,5000',
            startDate: '2027-04-01', days: 5, costPerMinute: 0, k: 1
        });
    }, /Unknown city 'Kyoto' on lodging line 1/);
});

test('parseData: Out-of-window dates skipped and counted', () => {
    const res = parseData({
        startCity: 'A', endCity: 'A',
        visitLines: 'B,1,1',
        transportLines: 'A,B,2027-04-01,T,10,10\nA,B,2027-04-10,T,10,10', // 2027-04-10 is day 9, out of window if days=5
        lodgingLines: 'B,2027-04-10,100',
        startDate: '2027-04-01', days: 5, costPerMinute: 0, k: 1
    });
    assert.strictEqual(res.skippedLines, 2);
});

test('parseData: Array index layout and round trip output decoding', () => {
    const res = parseData({
        startCity: 'A', endCity: 'C',
        visitLines: 'B,1,2',
        transportLines: 'A,B,2027-04-01,Flight,100,50\nB,C,2027-04-02,Train,200,60\nB,C,2027-04-02,Bus,50,120',
        lodgingLines: 'B,2027-04-01,1000\nB,2027-04-02,1200',
        startDate: '2027-04-01', days: 3, costPerMinute: 10, k: 1
    });
    
    assert.strictEqual(res.V, 1);
    assert.strictEqual(res.M, 3); // Flight, Train, Bus
    
    // mode 0: Flight, 1: Train, 2: Bus
    // N = 3. A=0, B=1, C=2.
    // A->B on day 0, mode 0 => ((0 * 3 + 1) * 3 + 0) * 3 + 0 = (1 * 3 + 0) * 3 + 0 = 9
    const idxAB = ((0 * 3 + 1) * 3 + 0) * 3 + 0;
    assert.strictEqual(res.priceArr[idxAB], 100);
    assert.strictEqual(res.minsArr[idxAB], 50);
    
    // B lodging on day 0 and day 1. B is node 1.
    assert.strictEqual(res.lodgingArr[1 * 3 + 0], 1000);
    assert.strictEqual(res.lodgingArr[1 * 3 + 1], 1200);

    // Mock an output array to test decodePlans
    const k = 1;
    // out_len = 1 * (4 + 1 + 6 * (1 + 1) + 1 + 4 * 1) = 4 + 1 + 12 + 1 + 4 = 22
    const outArray = new Float64Array(22);
    let ptr = 0;
    outArray[ptr++] = 1000; // obj
    outArray[ptr++] = 300;  // t_price
    outArray[ptr++] = 1000; // l_price
    outArray[ptr++] = 110;  // travel_mins
    
    outArray[ptr++] = 2; // legs
    outArray[ptr++] = 0; outArray[ptr++] = 1; outArray[ptr++] = 0; outArray[ptr++] = 0; outArray[ptr++] = 100; outArray[ptr++] = 50; // A->B
    outArray[ptr++] = 1; outArray[ptr++] = 2; outArray[ptr++] = 1; outArray[ptr++] = 1; outArray[ptr++] = 200; outArray[ptr++] = 60; // B->C
    
    outArray[ptr++] = 1; // stays
    outArray[ptr++] = 1; outArray[ptr++] = 0; outArray[ptr++] = 1; outArray[ptr++] = 1000; // B
    
    const plans = decodePlans(outArray, 1, 1, res.V, res.nodeToCity, res.modeIdxToName, res.startDate);
    assert.strictEqual(plans.length, 1);
    assert.strictEqual(plans[0].objective, 1000);
    assert.strictEqual(plans[0].legs.length, 2);
    assert.strictEqual(plans[0].legs[0].from, 'A');
    assert.strictEqual(plans[0].legs[0].to, 'B');
    assert.strictEqual(plans[0].legs[0].mode, 'Flight');
    assert.strictEqual(plans[0].stays.length, 1);
    assert.strictEqual(plans[0].stays[0].city, 'B');
});

test('WASM Engine: Example dataset validity check', async () => {
    // Gen example dataset
    const cities = ['Seoul', 'Tokyo', 'Osaka', 'Kyoto', 'Fukuoka'];
    let trans = "";
    let lodg = "";
    for (let d = 0; d < 14; d++) {
        const dateStr = `2027-04-${(d+1).toString().padStart(2, '0')}`;
        for (const c of cities) {
            if (c !== 'Seoul') lodg += `${c},${dateStr},${50000 + (c.length * 10000)}\n`;
        }
        for (let i = 0; i < cities.length; i++) {
            for (let j = 0; j < cities.length; j++) {
                if (i === j) continue;
                const c1 = cities[i];
                const c2 = cities[j];
                if (c1 === 'Seoul' || c2 === 'Seoul') {
                    trans += `${c1},${c2},${dateStr},Flight,${200000 + (d * 5000)},120\n`;
                } else {
                    trans += `${c1},${c2},${dateStr},Train,${10000 + (d * 1000)},60\n`;
                    trans += `${c1},${c2},${dateStr},Bus,${5000},180\n`;
                }
            }
        }
    }
    
    const parsed = parseData({
        startCity: 'Seoul', endCity: 'Seoul',
        visitLines: "Tokyo,2,3\nOsaka,1,2\nKyoto,2,3\nFukuoka,1,2",
        transportLines: trans,
        lodgingLines: lodg,
        startDate: '2027-04-01', days: 14, costPerMinute: 200, k: 5
    });
    
    const mod = await Module();
    
    const ptrPrice = mod._malloc(parsed.priceArr.length * 8);
    const ptrMinutes = mod._malloc(parsed.minsArr.length * 8);
    const ptrLodging = mod._malloc(parsed.lodgingArr.length * 8);
    const ptrStayMin = mod._malloc(parsed.stayMinArr.length * 4);
    const ptrStayMax = mod._malloc(parsed.stayMaxArr.length * 4);
    
    const out_len = parsed.k * (4 + 1 + 6 * (parsed.V + 1) + 1 + 4 * parsed.V);
    const ptrOut = mod._malloc(out_len * 8);
    
    mod.HEAPF64.set(parsed.priceArr, ptrPrice / 8);
    mod.HEAPF64.set(parsed.minsArr, ptrMinutes / 8);
    mod.HEAPF64.set(parsed.lodgingArr, ptrLodging / 8);
    mod.HEAP32.set(parsed.stayMinArr, ptrStayMin / 4);
    mod.HEAP32.set(parsed.stayMaxArr, ptrStayMax / 4);
    mod.HEAPF64.fill(0.0, ptrOut / 8, ptrOut / 8 + out_len);
    
    const numPlans = mod._trip_optimize(
        parsed.V, parsed.days, parsed.M,
        ptrPrice, ptrMinutes, ptrLodging,
        ptrStayMin, ptrStayMax,
        parsed.departMin, parsed.departMax, parsed.costPerMinute,
        parsed.k, ptrOut, out_len
    );
    
    if (numPlans < 0) {
        const errPtr = mod._trip_last_error();
        throw new Error(mod.UTF8ToString(errPtr));
    }
    
    const outActual = new Float64Array(mod.HEAPF64.subarray(ptrOut / 8, ptrOut / 8 + out_len));
    const plans = decodePlans(outActual, numPlans, parsed.k, parsed.V, parsed.nodeToCity, parsed.modeIdxToName, parsed.startDate);
    
    // Dump for the done_when D2 requirement
    console.log(`EXAMPLE DATASET PLANS: ${numPlans}`);
    if (plans.length > 0) {
        const p0 = plans[0];
        const visitsOrder = p0.stays.map(s => s.city).join(' -> ');
        console.log(`BEST PLAN ORDER: Seoul -> ${visitsOrder} -> Seoul`);
        console.log(`BEST PLAN TOTAL COST: ${p0.objective}`);
    }

    assert.ok(numPlans > 0, "Should find at least 1 plan");
    
    // Check V2 rules for all plans
    for (const plan of plans) {
        // No duplicate visits
        const visited = new Set(plan.stays.map(s => s.city));
        assert.strictEqual(visited.size, parsed.V, "Duplicate or missing visits");
        
        let sumTransport = 0;
        let sumLodging = 0;
        let sumMins = 0;
        
        for (const l of plan.legs) {
            sumTransport += l.price;
            sumMins += l.minutes;
        }
        for (const s of plan.stays) {
            sumLodging += s.price;
        }
        
        assert.strictEqual(plan.transport_price, sumTransport, "Transport price mismatch");
        assert.strictEqual(plan.lodging_price, sumLodging, "Lodging price mismatch");
        assert.strictEqual(plan.travel_minutes, sumMins, "Minutes mismatch");
        
        const expectedObj = sumTransport + sumLodging + (sumMins * parsed.costPerMinute);
        assert.strictEqual(plan.objective, expectedObj, "Objective recalculation mismatch");
    }
    
    mod._free(ptrPrice);
    mod._free(ptrMinutes);
    mod._free(ptrLodging);
    mod._free(ptrStayMin);
    mod._free(ptrStayMax);
    mod._free(ptrOut);
});
