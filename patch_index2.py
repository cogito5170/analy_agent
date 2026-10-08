import re

with open('trip_optimizer/web/index.html', 'r') as f:
    content = f.read()

# find btnExample event listener block and replace it
start_str = "document.getElementById('btnExample').addEventListener('click', () => {"
end_str = "        });"

start_idx = content.find(start_str)
end_idx = content.find(end_str, start_idx) + len(end_str)

new_block = """document.getElementById('btnExample').addEventListener('click', () => {
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

content = content[:start_idx] + new_block + content[end_idx:]

with open('trip_optimizer/web/index.html', 'w') as f:
    f.write(content)
