import re

with open('trip_optimizer/web/tests/model.test.mjs', 'r') as f:
    code = f.read()

code = code.replace("import { parseData, decodePlans } from '../model.mjs';", "import { parseData, decodePlans, encodeState, decodeState } from '../model.mjs';")

code = code.replace("""    assert.throws(() => {
        parseData({
            startCity: 'Seoul', endCity: 'Seoul',
            visitLines: 'Tokyo,1,2',
            transportLines: 'Seoul,Busan,2027-04-01,Bus,10,10',
            lodgingLines: '',
            startDate: '2027-04-01', days: 5, costPerMinute: 0, k: 1
        });
    }, /Unknown city 'Busan' on transport line 1/);""", """    try {
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
    }""")

code = code.replace("""    assert.throws(() => {
        parseData({
            startCity: 'Seoul', endCity: 'Seoul',
            visitLines: 'Tokyo,1,2',
            transportLines: 'Seoul,Tokyo,2027-04-01,Flight,10,10',
            lodgingLines: 'Kyoto,2027-04-01,5000',
            startDate: '2027-04-01', days: 5, costPerMinute: 0, k: 1
        });
    }, /Unknown city 'Kyoto' on lodging line 1/);""", """    try {
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
    }""")

code += """
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
"""

with open('trip_optimizer/web/tests/model.test.mjs', 'w') as f:
    f.write(code)

