import json, sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
n = 0
for rid, inn, email, body, pj in c.execute("SELECT id, inn, email, COALESCE(edited_body, body), panel_json FROM confirm_reviews WHERE status='pending' AND panel_json LIKE '%site_mismatch%' ORDER BY random() LIMIT 6"):
    p = json.loads(pj or "{}"); co = p.get("company") or {}
    print("#%d ИНН %s %s | компания: %s | сайт: %s" % (rid, inn, email, co.get("name") or co.get("company_name"), co.get("site") or co.get("website")))
    print("   ", (body or "").replace("\n", " ")[:330]); print()
