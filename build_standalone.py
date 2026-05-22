"""生成带管理功能的独立 HTML"""
import json

with open('/Users/doublle/Desktop/追星助手/star_tracker.db', 'rb') as f:
    pass  # we use sqlite3

import sqlite3
conn = sqlite3.connect('/Users/doublle/Desktop/追星助手/star_tracker.db')
conn.row_factory = sqlite3.Row

tmis = [dict(r) for r in conn.execute("SELECT * FROM tmis ORDER BY post_date DESC").fetchall()]
counselings = [dict(r) for r in conn.execute("SELECT * FROM counselings ORDER BY post_date DESC").fetchall()]
schedules = [dict(r) for r in conn.execute("SELECT * FROM schedules ORDER BY start_date DESC").fetchall()]
categories = [dict(r) for r in conn.execute("SELECT category, COUNT(*) as cnt FROM tmis GROUP BY category ORDER BY cnt DESC").fetchall()]

# Clean: remove sqlite-specific fields
for arr in [tmis, counselings, schedules]:
    for item in arr:
        for k in list(item.keys()):
            if k not in ('id','content','category','quote','post_url','post_date','post_likes',
                         'title','event_type','start_date','end_date','location','description'):
                del item[k]

conn.close()

tmis_json = json.dumps(tmis, ensure_ascii=False)
counselings_json = json.dumps(counselings, ensure_ascii=False)
schedules_json = json.dumps(schedules, ensure_ascii=False)
categories_json = json.dumps(categories, ensure_ascii=False)

print(f"Data: {len(tmis)} TMI, {len(counselings)} counseling, {len(schedules)} schedules")

# Read template
with open('/tmp/standalone_template.html') as f:
    template = f.read()

html = template.replace('{{TMIS_JSON}}', tmis_json)
html = html.replace('{{COUNSELINGS_JSON}}', counselings_json)
html = html.replace('{{SCHEDULES_JSON}}', schedules_json)
html = html.replace('{{CATEGORIES_JSON}}', categories_json)

with open('/Users/doublle/Desktop/追星助手/standalone.html', 'w', encoding='utf-8') as f:
    f.write(html)

import os
size = os.path.getsize('/Users/doublle/Desktop/追星助手/standalone.html')
print(f"Done: {size/1024:.0f}KB")
