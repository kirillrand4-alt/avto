# -*- coding: utf-8 -*-
"""10 случайных снятых линзой адресата в кампании 23: компания, продукция, фраза письма, причина линзы. Только чтение."""
import io, json, random, sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
а = {}
for с in io.open(r"C:\sender\_ops\gaz-kc-adresat-23.jsonl", encoding="utf-8"):
    try: з = json.loads(с); а[з["karta"]] = з
    except (ValueError, KeyError): pass
р = c.execute("SELECT id, body, panel_json FROM confirm_reviews WHERE campaign_id=23 AND status='skipped' AND reason LIKE 'линза адресат%'").fetchall()
random.seed(16)
for кид, б, pj in random.sample(р, 10):
    д = json.loads(pj or "{}"); к = д.get("company") or {}
    print("\n#%s %s\n  продукция: %s\n  фраза: %s\n  линза: %s" % (кид, к.get("name", ""), (к.get("activity") or "")[:220], б.split("\n\n")[1].split(". ")[0][:200],
          str(а.get(кид, {}).get("problem") or а.get(кид, {}).get("pochemu") or "")[:200]))
