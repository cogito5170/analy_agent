export function parseData({
    startCity,
    endCity,
    visitLines,
    transportLines,
    lodgingLines,
    startDate, // YYYY-MM-DD
    days,
    k,
    costPerHour
}) {
    function throwError(inputId, lineNum, msg) {
        const e = new Error(msg);
        e.inputId = inputId;
        e.lineNum = lineNum;
        throw e;
    }

    if (costPerHour === '' || costPerHour === null || costPerHour === undefined || isNaN(Number(costPerHour)) || Number(costPerHour) < 0) {
        throwError('costPerHour', null, "must be a non-negative number");
    }
    const costPerMinute = Math.round(Number(costPerHour) / 60);

    // 1. Visit Cities (방문 도시)
    // Format: city,min_stay,max_stay
    const visits = [];
    const cities = new Map();
    cities.set(startCity, 0); // 0 = start
    
    // To handle line numbers properly, we will split and map
    const splitLines = (text) => text.split(/\r?\n/).map((line, i) => ({ text: line.trim(), lineNum: i + 1 })).filter(l => l.text.length > 0);
    
    const visitItems = splitLines(visitLines);
    if (visitItems.length > 10) {
        throwError('visitLines', null, 'Too many visit cities (max 10).');
    }
    
    for (const item of visitItems) {
        const parts = item.text.split(',');
        if (parts.length < 3) throwError('visitLines', item.lineNum, `Visit city format error`);
        const name = parts[0].trim();
        const min = parseInt(parts[1], 10);
        const max = parseInt(parts[2], 10);
        if (cities.has(name)) throwError('visitLines', item.lineNum, `Duplicate city ${name}`);
        visits.push({ name, min, max });
        cities.set(name, visits.length); // 1..V
    }
    
    const V = visits.length;
    if (!cities.has(endCity)) {
        cities.set(endCity, V + 1); // V+1 = end
    }
    
    const N = V + 2;
    const startMs = new Date(startDate).getTime();
    
    function getDayIndex(dateStr) {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return -1;
        const diffMs = d.getTime() - startMs;
        const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24));
        return diffDays;
    }
    
    const modes = new Map();
    let modesCount = 0;
    
    let skippedTransport = 0;
    const transItems = splitLines(transportLines);
    const transData = [];
    
    for (const item of transItems) {
        // 출발도시,도착도시,날짜(YYYY-MM-DD),수단,가격(원),소요분
        const parts = item.text.split(',');
        if (parts.length < 6) throwError('transportLines', item.lineNum, `Transport format error`);
        const [from, to, dateStr, mode, priceStr, minsStr] = parts.map(p => p.trim());
        
        let fromIdx = -1, toIdx = -1;
        
        if (from === startCity) fromIdx = 0;
        else if (cities.has(from)) fromIdx = cities.get(from);
        
        if (to === endCity) toIdx = V + 1;
        else if (cities.has(to) && to !== startCity) toIdx = cities.get(to); // to cannot be start city node 0
        
        if (fromIdx === -1 && from !== startCity && !cities.has(from)) throwError('transportLines', item.lineNum, `Unknown city '${from}'`);
        if (toIdx === -1 && to !== endCity && !cities.has(to)) throwError('transportLines', item.lineNum, `Unknown city '${to}'`);
        
        const dayIdx = getDayIndex(dateStr);
        if (dayIdx < 0 || dayIdx >= days) {
            skippedTransport++;
            continue;
        }
        
        if (!modes.has(mode)) {
            modes.set(mode, modesCount++);
        }
        const mIdx = modes.get(mode);
        const price = parseInt(priceStr, 10);
        const mins = parseInt(minsStr, 10);
        
        if (fromIdx !== -1 && toIdx !== -1) {
            transData.push({ from: fromIdx, to: toIdx, day: dayIdx, mode: mIdx, price, mins });
        }
    }
    
    const M = Math.max(1, modesCount);
    
    // Flat arrays initialization
    const legsCount = N * N * days * M;
    const priceArr = new Float64Array(legsCount);
    priceArr.fill(-1); // negative means option doesn't exist
    const minsArr = new Float64Array(legsCount);
    minsArr.fill(0);
    
    for (const t of transData) {
        // ((a × N + b) × D + day) × M + mode
        const idx = ((t.from * N + t.to) * days + t.day) * M + t.mode;
        priceArr[idx] = t.price;
        minsArr[idx] = t.mins;
    }
    
    let skippedLodging = 0;
    const lodgingItems = lodgingLines ? splitLines(lodgingLines) : [];
    
    const lodgingArr = new Float64Array(N * days);
    lodgingArr.fill(0); // 0 by default
    
    for (const item of lodgingItems) {
        // 도시,날짜,1박가격(원)
        const parts = item.text.split(',');
        if (parts.length < 3) throwError('lodgingLines', item.lineNum, `Lodging format error`);
        const [city, dateStr, priceStr] = parts.map(p => p.trim());
        
        let cIdx = -1;
        if (city === startCity) cIdx = 0;
        else if (city === endCity) cIdx = V + 1;
        else if (cities.has(city)) cIdx = cities.get(city);
        
        if (cIdx === -1) throwError('lodgingLines', item.lineNum, `Unknown city '${city}'`);
        
        const dayIdx = getDayIndex(dateStr);
        if (dayIdx < 0 || dayIdx >= days) {
            skippedLodging++;
            continue;
        }
        
        const price = parseInt(priceStr, 10);
        lodgingArr[cIdx * days + dayIdx] = price;
    }
    
    const stayMinArr = new Int32Array(N);
    const stayMaxArr = new Int32Array(N);
    stayMinArr.fill(0);
    stayMaxArr.fill(0);
    
    for (let i = 0; i < V; i++) {
        stayMinArr[i + 1] = visits[i].min;
        stayMaxArr[i + 1] = visits[i].max;
    }
    
    const nodeToCity = new Array(N);
    nodeToCity[0] = startCity;
    nodeToCity[V + 1] = endCity;
    for (let i = 0; i < V; i++) nodeToCity[i + 1] = visits[i].name;
    
    const modeIdxToName = new Array(M);
    for (const [name, idx] of modes.entries()) {
        modeIdxToName[idx] = name;
    }
    if (M === 1 && modesCount === 0) modeIdxToName[0] = "Default";
    
    return {
        V, days, M,
        priceArr, minsArr, lodgingArr, stayMinArr, stayMaxArr,
        departMin: 0, departMax: days - 1,
        costPerMinute, k,
        skippedLines: skippedTransport + skippedLodging,
        nodeToCity,
        modeIdxToName,
        startDate
    };
}

export function decodePlans(outArray, numPlans, k, V, nodeToCity, modeIdxToName, startDateStr) {
    const plans = [];
    let ptr = 0;
    
    const startMs = new Date(startDateStr).getTime();
    function formatDay(dayIdx) {
        const d = new Date(startMs + dayIdx * 24 * 60 * 60 * 1000);
        return d.toISOString().split('T')[0];
    }
    
    for (let i = 0; i < numPlans; i++) {
        if (ptr >= outArray.length) break;
        
        const objective = outArray[ptr++];
        const transport_price = outArray[ptr++];
        const lodging_price = outArray[ptr++];
        const travel_minutes = outArray[ptr++];
        const numLegs = outArray[ptr++];
        
        const legs = [];
        for (let l = 0; l < numLegs; l++) {
            const from = outArray[ptr++];
            const to = outArray[ptr++];
            const day = outArray[ptr++];
            const mode = outArray[ptr++];
            const price = outArray[ptr++];
            const minutes = outArray[ptr++];
            legs.push({
                from: nodeToCity[from],
                to: nodeToCity[to],
                date: formatDay(day),
                mode: modeIdxToName[mode],
                price,
                minutes
            });
        }
        
        const numStays = outArray[ptr++];
        const stays = [];
        for (let s = 0; s < numStays; s++) {
            const city = outArray[ptr++];
            const arrive_day = outArray[ptr++];
            const nights = outArray[ptr++];
            const lodging = outArray[ptr++];
            stays.push({
                city: nodeToCity[city],
                arriveDate: formatDay(arrive_day),
                nights,
                price: lodging
            });
        }
        
        plans.push({
            objective,
            transport_price,
            lodging_price,
            travel_minutes,
            legs,
            stays
        });
    }
    
    return plans;
}
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
    
    let ptrPrice = 0;
    let ptrMinutes = 0;
    let ptrLodging = 0;
    let ptrStayMin = 0;
    let ptrStayMax = 0;
    let ptrOut = 0;
    
    try {
        ptrPrice = mod._malloc(p.priceArr.length * 8);
        ptrMinutes = mod._malloc(p.minsArr.length * 8);
        ptrLodging = mod._malloc(p.lodgingArr.length * 8);
        ptrStayMin = mod._malloc(p.stayMinArr.length * 4);
        ptrStayMax = mod._malloc(p.stayMaxArr.length * 4);
        
        const out_len = mod._trip_output_size(p.V, p.k);
        if (out_len <= 0) {
            throw new Error("Invalid output size");
        }
        ptrOut = mod._malloc(out_len * 8);
        
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
            throw new Error(errStr);
        }
        
        const outActual = new Float64Array(mod.HEAPF64.subarray(ptrOut / 8, ptrOut / 8 + out_len));
        const plans = decodePlans(outActual, numPlans, p.k, p.V, p.nodeToCity, p.modeIdxToName, p.startDate);
        
        return plans;
    } finally {
        if (ptrPrice) mod._free(ptrPrice);
        if (ptrMinutes) mod._free(ptrMinutes);
        if (ptrLodging) mod._free(ptrLodging);
        if (ptrStayMin) mod._free(ptrStayMin);
        if (ptrStayMax) mod._free(ptrStayMax);
        if (ptrOut) mod._free(ptrOut);
    }
}

export function encodeState(state) {
    return btoa(encodeURIComponent(JSON.stringify(state)));
}
export function decodeState(hash) {
    if (!hash || hash.length < 2) return null;
    try {
        const obj = JSON.parse(decodeURIComponent(atob(hash.startsWith('#') ? hash.substring(1) : hash)));
        if (obj && typeof obj === 'object') {
            if (obj.costPerHour === undefined && obj.costPerMinute !== undefined) {
                obj.costPerHour = obj.costPerMinute * 60;
            }
        }
        return obj;
    } catch(e) {
        return null;
    }
}
