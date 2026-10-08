export function getExampleData() {
    const startCity = 'Seoul';
    const endCity = 'Seoul';
    const startDate = '2027-04-01';
    const days = 14;
    const visitLines = "Tokyo,2,3\nOsaka,1,2\nKyoto,2,3\nFukuoka,1,2";
    
    const cities = ['Seoul', 'Tokyo', 'Osaka', 'Kyoto', 'Fukuoka'];
    let transportLines = "";
    let lodgingLines = "";
    
    for (let d = 0; d < 14; d++) {
        const dateStr = `2027-04-${(d+1).toString().padStart(2, '0')}`;
        for (const c of cities) {
            if (c !== 'Seoul') lodgingLines += `${c},${dateStr},${50000 + (c.length * 10000)}\n`;
        }
        for (let i = 0; i < cities.length; i++) {
            for (let j = 0; j < cities.length; j++) {
                if (i === j) continue;
                const c1 = cities[i];
                const c2 = cities[j];
                if (c1 === 'Seoul' || c2 === 'Seoul') {
                    transportLines += `${c1},${c2},${dateStr},Flight,${200000 + (d * 5000)},120\n`;
                } else {
                    transportLines += `${c1},${c2},${dateStr},Train,${10000 + (d * 1000)},60\n`;
                    transportLines += `${c1},${c2},${dateStr},Bus,${5000},180\n`;
                }
            }
        }
    }
    
    return {
        startCity, endCity, startDate, days, visitLines, transportLines, lodgingLines
    };
}

export function callEngine(mod, parsed) {
    const p = parsed;
    
    const ptrPrice = mod._malloc(p.priceArr.length * 8);
    const ptrMinutes = mod._malloc(p.minsArr.length * 8);
    const ptrLodging = mod._malloc(p.lodgingArr.length * 8);
    const ptrStayMin = mod._malloc(p.stayMinArr.length * 4);
    const ptrStayMax = mod._malloc(p.stayMaxArr.length * 4);
    
    const out_len = mod._trip_output_size(p.V, p.k);
    if (out_len <= 0) {
        mod._free(ptrPrice); mod._free(ptrMinutes); mod._free(ptrLodging); mod._free(ptrStayMin); mod._free(ptrStayMax);
        throw new Error("Invalid output size");
    }
    const ptrOut = mod._malloc(out_len * 8);
    
    mod.HEAPF64.set(p.priceArr, ptrPrice / 8);
    mod.HEAPF64.set(p.minsArr, ptrMinutes / 8);
    mod.HEAPF64.set(p.lodgingArr, ptrLodging / 8);
    mod.HEAP32.set(p.stayMinArr, ptrStayMin / 4);
    mod.HEAP32.set(p.stayMaxArr, ptrStayMax / 4);
    mod.HEAPF64.fill(0.0, ptrOut / 8, ptrOut / 8 + out_len);
    
    const numPlans = mod._trip_optimize(
        p.V, p.days, p.M,
        ptrPrice, ptrMinutes, ptrLodging,
        ptrStayMin, ptrStayMax,
        p.departMin, p.departMax, p.costPerMinute,
        p.k, ptrOut, out_len
    );
    
    if (numPlans < 0) {
        const errPtr = mod._trip_last_error();
        const errStr = mod.UTF8ToString(errPtr);
        mod._free(ptrPrice); mod._free(ptrMinutes); mod._free(ptrLodging); mod._free(ptrStayMin); mod._free(ptrStayMax); mod._free(ptrOut);
        throw new Error(errStr);
    }
    
    const outActual = new Float64Array(mod.HEAPF64.subarray(ptrOut / 8, ptrOut / 8 + out_len));
    const plans = decodePlans(outActual, numPlans, p.k, p.V, p.nodeToCity, p.modeIdxToName, p.startDate);
    
    mod._free(ptrPrice); mod._free(ptrMinutes); mod._free(ptrLodging); mod._free(ptrStayMin); mod._free(ptrStayMax); mod._free(ptrOut);
    
    return plans;
}
