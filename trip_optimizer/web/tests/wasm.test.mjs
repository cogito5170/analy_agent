import test from 'node:test';
import assert from 'node:assert';
import { parseData, callEngine, getExampleData } from '../model.mjs';
import Module from '../../engine/build_wasm/engine.mjs';

test('WASM Engine: Example dataset validity check', async () => {
    const data = getExampleData();
    data.costPerMinute = 200;
    data.k = 5;
    
    const parsed = parseData(data);
    const mod = await Module();
    const plans = callEngine(mod, parsed);
    const numPlans = plans.length;
    
    // Dump for the done_when D2 requirement
    console.log(`EXAMPLE DATASET PLANS: ${numPlans}`);
    if (plans.length > 0) {
        const p0 = plans[0];
        const visitsOrder = p0.stays.map(s => s.city).join(' -> ');
        console.log(`BEST PLAN ORDER: ${p0.legs[0].from} -> ${visitsOrder} -> ${p0.legs[p0.legs.length-1].to}`);
        console.log(`BEST PLAN TOTAL COST: ${p0.objective}`);
        console.log(`BEST PLAN TRANSPORT COST: ${p0.transport_price}`);
        console.log(`BEST PLAN LODGING COST: ${p0.lodging_price}`);
        console.log(`BEST PLAN MINUTES: ${p0.travel_minutes}`);
    }

    assert.ok(numPlans > 0, "Should find at least 1 plan");
    
    for (const plan of plans) {
        // V2 rule checks
        // 1. distinct cities and sums
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
        
        // 2. start and end city
        assert.strictEqual(plan.legs[0].from, data.startCity, "Start city mismatch");
        assert.strictEqual(plan.legs[plan.legs.length - 1].to, data.endCity, "End city mismatch");
        
        // 3. each leg's date chained to stays
        let currentMs = new Date(plan.legs[0].date).getTime();
        for (let i = 0; i < plan.stays.length; i++) {
            const stay = plan.stays[i];
            const legTo = plan.legs[i];
            const legFrom = plan.legs[i + 1];
            
            // Arrival day check
            assert.strictEqual(new Date(stay.arriveDate).getTime(), new Date(legTo.date).getTime(), "Leg date doesn't match arrival date");
            
            // Next departure day check
            const nextDepartureMs = new Date(stay.arriveDate).getTime() + stay.nights * 24 * 60 * 60 * 1000;
            assert.strictEqual(new Date(legFrom.date).getTime(), nextDepartureMs, "Nights don't match departure date");
        }
        
        // 4. nights inside each city's range
        for (const stay of plan.stays) {
            const nodeIdx = parsed.nodeToCity.indexOf(stay.city);
            const minStay = parsed.stayMinArr[nodeIdx];
            const maxStay = parsed.stayMaxArr[nodeIdx];
            assert.ok(stay.nights >= minStay && stay.nights <= maxStay, `Stay out of range for ${stay.city}`);
        }
        
        // 5. departure inside window
        const windowEndMs = new Date(data.startDate).getTime() + data.days * 24 * 60 * 60 * 1000;
        for (const leg of plan.legs) {
            const t = new Date(leg.date).getTime();
            assert.ok(t >= new Date(data.startDate).getTime() && t < windowEndMs, "Departure outside window");
        }
        
        // 6. every leg present in input CSV with same price and mins
        for (const leg of plan.legs) {
            const lines = data.transportLines.split('\n');
            let found = false;
            for (const line of lines) {
                if (!line.trim()) continue;
                const parts = line.split(',');
                if (parts[0] === leg.from && parts[1] === leg.to && parts[2] === leg.date && parts[3] === leg.mode && parseInt(parts[4]) === leg.price && parseInt(parts[5]) === leg.minutes) {
                    found = true;
                    break;
                }
            }
            assert.ok(found, `Leg ${leg.from}->${leg.to} on ${leg.date} with mode ${leg.mode} not found or mismatched`);
        }
    }
});
