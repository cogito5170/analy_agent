import re

with open('trip_optimizer/web/index.html', 'r') as f:
    content = f.read()

content = content.replace("import { parseData, decodePlans } from './model.mjs';", "import { parseData, getExampleData } from './model.mjs';")

example_func = """
        document.getElementById('btnExample').addEventListener('click', () => {
            document.getElementById('exampleNote').style.display = 'block';
            
            const data = getExampleData();
            document.getElementById('startCity').value = data.startCity;
            document.getElementById('endCity').value = data.endCity;
            document.getElementById('startDate').value = data.startDate;
            document.getElementById('days').value = data.days;
            document.getElementById('visitLines').value = data.visitLines;
            document.getElementById('transportLines').value = data.transportLines;
            document.getElementById('lodgingLines').value = data.lodgingLines;
        });"""

content = re.sub(r"document\.getElementById\('btnExample'\)\.addEventListener\('click', \(\) => \{.*?\ndocument\.getElementById\('lodgingLines'\)\.value = lodg;\n\s*\}\);", example_func.strip(), content, flags=re.DOTALL)

# update optimize button logic where it calls decodePlans
content = content.replace("const plans = decodePlans(res.outArray, res.numPlans, 5, parsed.V, parsed.nodeToCity, parsed.modeIdxToName, parsed.startDate);", "const plans = res.plans;")

with open('trip_optimizer/web/index.html', 'w') as f:
    f.write(content)
