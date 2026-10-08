import Module from './engine.mjs';

let modPromise = null;

self.onmessage = async (e) => {
    const data = e.data;
    if (data.type === 'init') {
        if (!modPromise) {
            modPromise = Module();
        }
        await modPromise;
        self.postMessage({ type: 'ready' });
    } else if (data.type === 'optimize') {
        try {
            const mod = await modPromise;
            
            const p = data.payload;
            
            const ptrPrice = mod._malloc(p.priceArr.length * 8);
            const ptrMinutes = mod._malloc(p.minsArr.length * 8);
            const ptrLodging = mod._malloc(p.lodgingArr.length * 8);
            const ptrStayMin = mod._malloc(p.stayMinArr.length * 4);
            const ptrStayMax = mod._malloc(p.stayMaxArr.length * 4);
            
            const N = p.V + 2;
            const out_len = p.k * (4 + 1 + 6 * (p.V + 1) + 1 + 4 * p.V);
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
                // error
                const errPtr = mod._trip_last_error();
                const errStr = mod.UTF8ToString(errPtr);
                self.postMessage({ type: 'error', error: errStr });
            } else {
                const outActual = new Float64Array(mod.HEAPF64.subarray(ptrOut / 8, ptrOut / 8 + out_len));
                self.postMessage({ type: 'success', numPlans, outArray: outActual });
            }
            
            mod._free(ptrPrice);
            mod._free(ptrMinutes);
            mod._free(ptrLodging);
            mod._free(ptrStayMin);
            mod._free(ptrStayMax);
            mod._free(ptrOut);
        } catch (err) {
            self.postMessage({ type: 'error', error: err.message || String(err) });
        }
    }
};
