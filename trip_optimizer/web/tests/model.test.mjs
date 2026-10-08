import test from 'node:test';
import assert from 'node:assert';
import { parseData, decodePlans, encodeState, decodeState } from '../model.mjs';

test('parseData: CSV parsing and error line numbers', () => {
    // Unknown city on transport
    try {
        parseData({
            startCity: 'Seoul', endCity: 'Seoul',
            visitLines: 'Tokyo,1,2',
            transportLines: 'Seoul,Busan,2027-04-01,Bus,10,10',
            lodgingLines: '',
            startDate: '2027-04-01', days: 5, costPerMinute: 0, k: 1
        });
        assert.fail('Should throw');
    } catch(err) {
        assert.strictEqual(err.inputId, 'transportLines');
        assert.strictEqual(err.lineNum, 1);
        assert.match(err.message, /Unknown city 'Busan'/);
    }

    // Unknown city on lodging
    try {
        parseData({
            startCity: 'Seoul', endCity: 'Seoul',
            visitLines: 'Tokyo,1,2',
            transportLines: 'Seoul,Tokyo,2027-04-01,Flight,10,10',
            lodgingLines: 'Kyoto,2027-04-01,5000',
            startDate: '2027-04-01', days: 5, costPerMinute: 0, k: 1
        });
        assert.fail('Should throw');
    } catch(err) {
        assert.strictEqual(err.inputId, 'lodgingLines');
        assert.strictEqual(err.lineNum, 1);
        assert.match(err.message, /Unknown city 'Kyoto'/);
    }
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


test('F6 Share link: encode then decode gives the same input', () => {
    const input = {
        startCity: 'Seoul', endCity: 'Tokyo',
        visitLines: 'Osaka,1,2',
        transportLines: 'Seoul,Osaka,2027-04-01,Flight,10,10',
        lodgingLines: 'Osaka,2027-04-01,5000',
        startDate: '2027-04-01', days: 5, costPerMinute: 200, k: 5
    };
    const hash = encodeState(input);
    const decoded = decodeState(hash);
    assert.deepStrictEqual(decoded, input);
});
