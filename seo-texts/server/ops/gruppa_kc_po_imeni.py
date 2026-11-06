# -*- coding: utf-8 -*-
"""Получателям карточек кампании «КЦ по имени 06.11» дописать группу «КЦ по имени» в extra.gruppy
(фильтр «группа» в «Подтвердить отправку»). [--primenit]"""
import json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
кид = c.execute("SELECT id FROM campaigns WHERE name='КЦ по имени 06.11'").fetchone()[0]
р = c.execute("SELECT DISTINCT r.id, r.extra_json FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id WHERE cr.campaign_id=?", (кид,)).fetchall()
обн = []
for rid, ex in р:
    x = json.loads(ex or "{}"); г = list(x.get("gruppy") or [])
    if "КЦ по имени" not in г:
        x["gruppy"] = г + ["КЦ по имени"]; обн.append((json.dumps(x, ensure_ascii=False), rid))
print("получателей:", len(р), "| дописать группу:", len(обн))
if "--primenit" in sys.argv:
    with c:
        c.executemany("UPDATE recipients SET extra_json=? WHERE id=?", обн)
    print("применено")
