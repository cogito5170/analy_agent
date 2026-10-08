import re

with open('trip_optimizer/web/model.mjs', 'r') as f:
    code = f.read()

# Add throwError helper at the beginning of parseData
code = code.replace("const visits = [];", """
    function throwError(inputId, lineNum, msg) {
        const e = new Error(msg);
        e.inputId = inputId;
        e.lineNum = lineNum;
        throw e;
    }
    const visits = [];
""".strip())

# Replace specific errors
code = code.replace('throw new Error("Too many visit cities (max 10).");', "throwError('visitLines', null, 'Too many visit cities (max 10).');")
code = code.replace('throw new Error(`Visit city format error on line ${item.lineNum}`);', "throwError('visitLines', item.lineNum, `Visit city format error`);")
code = code.replace('throw new Error(`Duplicate city ${name} on line ${item.lineNum}`);', "throwError('visitLines', item.lineNum, `Duplicate city ${name}`);")

code = code.replace('throw new Error(`Transport format error on line ${item.lineNum}`);', "throwError('transportLines', item.lineNum, `Transport format error`);")
code = code.replace("if (fromIdx === -1 && from !== startCity && !cities.has(from)) throw new Error(`Unknown city '${from}' on transport line ${item.lineNum}`);", "if (fromIdx === -1 && from !== startCity && !cities.has(from)) throwError('transportLines', item.lineNum, `Unknown city '${from}'`);")
code = code.replace("if (toIdx === -1 && to !== endCity && !cities.has(to)) throw new Error(`Unknown city '${to}' on transport line ${item.lineNum}`);", "if (toIdx === -1 && to !== endCity && !cities.has(to)) throwError('transportLines', item.lineNum, `Unknown city '${to}'`);")

code = code.replace('throw new Error(`Lodging format error on line ${item.lineNum}`);', "throwError('lodgingLines', item.lineNum, `Lodging format error`);")
code = code.replace("if (cIdx === -1) throw new Error(`Unknown city '${city}' on lodging line ${item.lineNum}`);", "if (cIdx === -1) throwError('lodgingLines', item.lineNum, `Unknown city '${city}'`);")

with open('trip_optimizer/web/model.mjs', 'w') as f:
    f.write(code)
