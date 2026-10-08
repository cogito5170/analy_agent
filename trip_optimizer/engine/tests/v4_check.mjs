import Module from '../build_wasm/engine.mjs';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function run() {
    const mod = await Module();
    const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'v4_reference.json'), 'utf8'));

    let problems = 0;
    let mismatches = 0;

    for (const p of data) {
        problems++;
        
        const ptrPrice = mod._malloc(p.price.length * 8);
        const ptrMinutes = mod._malloc(p.minutes.length * 8);
        const ptrLodging = mod._malloc(p.lodging.length * 8);
        const ptrStayMin = mod._malloc(p.stay_min.length * 4);
        const ptrStayMax = mod._malloc(p.stay_max.length * 4);
        const ptrOut = mod._malloc(p.out_len * 8);
        
        mod.HEAPF64.set(p.price, ptrPrice / 8);
        mod.HEAPF64.set(p.minutes, ptrMinutes / 8);
        mod.HEAPF64.set(p.lodging, ptrLodging / 8);
        mod.HEAP32.set(p.stay_min, ptrStayMin / 4);
        mod.HEAP32.set(p.stay_max, ptrStayMax / 4);
        
        // Zero-initialize out array
        mod.HEAPF64.fill(0.0, ptrOut / 8, ptrOut / 8 + p.out_len);
        
        const n = mod._trip_optimize(
            p.visits, p.days, p.modes,
            ptrPrice, ptrMinutes, ptrLodging,
            ptrStayMin, ptrStayMax,
            p.depart_min, p.depart_max, p.cost_per_minute,
            p.k, ptrOut, p.out_len
        );
        
        let mismatch = false;
        if (n !== p.expected_n) {
            console.error(`Problem ${problems}: Mismatch in n: got ${n}, expected ${p.expected_n}`);
            if (n === -1) {
                // To get error: we need UTF8 string from C
                // But we don't have to print it to know it's a mismatch.
            }
            mismatch = true;
        } else if (n > 0 || p.out_len > 0) { // check out array even if n <= 0, in case of buffer overwrite? The spec says exactly compare.
            const outActual = mod.HEAPF64.subarray(ptrOut / 8, ptrOut / 8 + p.out_len);
            for (let i = 0; i < p.out_len; i++) {
                if (outActual[i] !== p.expected_out[i]) {
                    console.error(`Problem ${problems}: Mismatch in out[${i}]: got ${outActual[i]}, expected ${p.expected_out[i]}`);
                    mismatch = true;
                    break;
                }
            }
        }
        
        if (mismatch) mismatches++;
        
        mod._free(ptrPrice);
        mod._free(ptrMinutes);
        mod._free(ptrLodging);
        mod._free(ptrStayMin);
        mod._free(ptrStayMax);
        mod._free(ptrOut);
    }
    
    console.log(`V4 result: ${problems} problems, ${mismatches} mismatches`);
    if (mismatches > 0) {
        process.exit(1);
    }
}

run().catch(err => {
    console.error(err);
    process.exit(1);
});
