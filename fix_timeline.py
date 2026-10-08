import re

with open('trip_optimizer/web/index.html', 'r') as f:
    html = f.read()

old_timeline = """                    // Timeline
                    const timelineUl = el('ul', null);
                    // Just listing legs is enough for timeline
                    plan.legs.forEach(l => {
                        timelineUl.appendChild(el('li', `${l.date}: ${l.from} -> ${l.to} (${l.mode}, ${l.minutes} min)`));
                    });
                    div.appendChild(el('h5', 'Timeline'));
                    div.appendChild(timelineUl);"""

new_timeline = """                    // Timeline
                    const timelineUl = el('ul', null);
                    const timelineEvents = [];
                    plan.legs.forEach(l => timelineEvents.push({ date: l.date, text: `${l.from} -> ${l.to} (${l.mode}, ${l.minutes} min)` }));
                    plan.stays.forEach(s => timelineEvents.push({ date: s.arriveDate, text: `Stay in ${s.city} (${s.nights} nights)` }));
                    timelineEvents.sort((a, b) => a.date.localeCompare(b.date));
                    timelineEvents.forEach(e => {
                        timelineUl.appendChild(el('li', `${e.date}: ${e.text}`));
                    });
                    div.appendChild(el('h5', 'Timeline'));
                    div.appendChild(timelineUl);"""

html = html.replace(old_timeline, new_timeline)

with open('trip_optimizer/web/index.html', 'w') as f:
    f.write(html)
