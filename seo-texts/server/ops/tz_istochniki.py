import json, sqlite3
from collections import Counter
o = sqlite3.connect(r"C:\sender\obzvon-index.db"); e = sqlite3.connect(r"C:\sender\enrich.db")
print("obzvon:", [r[1] for r in o.execute("PRAGMA table_info(obzvon)")])
print("site_facts:", [r[1] for r in e.execute("PRAGMA table_info(site_facts)")])
k = Counter()
for (fj,) in e.execute("SELECT facts_json FROM site_facts LIMIT 3000"):
    try: k.update(json.loads(fj or "{}").keys())
    except Exception: pass
print(k.most_common(30))
c = sqlite3.connect(r"C:\sender\sender.db")
print("recipients:", [r[1] for r in c.execute("PRAGMA table_info(recipients)")])
for (ex,) in c.execute("SELECT r.extra_json FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id=14 AND m.status='scheduled' AND length(r.inn)=11 LIMIT 2"):
    print(ex[:600])
