"""生成内嵌数据的独立 HTML"""
import json, sqlite3, os

conn = sqlite3.connect('/Users/doublle/Desktop/追星助手/star_tracker.db')
conn.row_factory = sqlite3.Row

tmis = [dict(r) for r in conn.execute("SELECT * FROM tmis ORDER BY post_date DESC").fetchall()]
counselings = [dict(r) for r in conn.execute("SELECT * FROM counselings ORDER BY post_date DESC").fetchall()]
categories = [dict(r) for r in conn.execute("SELECT category, COUNT(*) as cnt FROM tmis GROUP BY category ORDER BY cnt DESC").fetchall()]

keep_keys = {'id','content','category','categories','quote','post_url','post_date','post_likes',
             'title','event_type','start_date','end_date','location','description'}
for arr in [tmis, counselings]:
    for item in arr:
        for k in list(item.keys()):
            if k not in keep_keys:
                del item[k]

tag_row = conn.execute("SELECT value FROM meta WHERE key = 'tmi_tags'").fetchone()
custom_tags_json = tag_row['value'] if tag_row else 'null'

conn.close()

tmis_json = json.dumps(tmis, ensure_ascii=False)
counselings_json = json.dumps(counselings, ensure_ascii=False)
categories_json = json.dumps(categories, ensure_ascii=False)

print(f"Data: {len(tmis)} TMI, {len(counselings)} counseling")

# Read template
with open('/tmp/standalone_template.html') as f:
    template = f.read()

# Read splash image base64
with open('/tmp/splash_b64.txt') as f:
    splash_b64 = f.read().strip()

html = template.replace('SPLASH_B64', splash_b64)
html = html.replace('{{TMIS_JSON}}', tmis_json)
html = html.replace('{{COUNSELINGS_JSON}}', counselings_json)
html = html.replace('{{CATEGORIES_JSON}}', categories_json)
html = html.replace('{{CUSTOM_TAGS_JSON}}', custom_tags_json)

output_path = '/Users/doublle/Desktop/追星助手/standalone.html'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

size = os.path.getsize(output_path)
print(f"Done: {size/1024:.0f}KB")
