# -*- coding: utf-8 -*-
"""Карточкам из списка spisok-kc-iz-9000.json ставит extra.target_division=kc
(вердикт классификатора «кц», владелец 15.10). Печатает число ящиков пула КЦ.
Без --katit — только счёт."""
import io, json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
рид = json.load(io.open(r"C:\sender\_ops\spisok-kc-iz-9000.json"))
n = 0
with c:
    for r in рид:
        row = c.execute("SELECT extra_json FROM recipients WHERE id=?", (r,)).fetchone()
        ex = json.loads(row[0] or "{}") if row else {}
        if ex.get("target_division") == "kc":
            continue
        n += 1
        if "--katit" in sys.argv:
            ex["target_division_bylo"] = ex.get("target_division")
            ex["target_division"] = "kc"
            ex["target_division_istochnik"] = "вердикт кц, владелец 15.10"
            c.execute("UPDATE recipients SET extra_json=? WHERE id=?", (json.dumps(ex, ensure_ascii=False), r))
print("к смене на kc:", n, "из", len(рид))
кол = [x[1] for x in c.execute("PRAGMA table_info(mailboxes)")]
print("колонки ящиков:", кол)
for k in ("pool", "provider_pool", "segment", "division"):
    if k in кол:
        print(k, c.execute("SELECT %s, COUNT(*) FROM mailboxes GROUP BY 1" % k).fetchall())
