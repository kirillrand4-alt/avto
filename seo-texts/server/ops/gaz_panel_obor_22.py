# -*- coding: utf-8 -*-
"""Панель карточек кампании 22: поле company.why_equipment с обоснованием Meyer («фотосепараторы/рентген» — панель
подставила по направлению компании в базе) заменить на газовое (данные ЦА: техпроцесс отрасли/фраза письма).
Текст письма не трогаем.  gaz_panel_obor_22.py [--primenit]"""
import json, re, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
n = 0
for кид, pj in c.execute("SELECT id, panel_json FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall():
    д = json.loads(pj or "{}"); к = д.get("company") or {}
    if not re.search(r"(?i)фотосепаратор|рентген", str(к.get("why_equipment") or "")): continue
    г = д.get("gaz") or {}
    к["why_equipment"] = "Газ (%s): %s" % (г.get("gaz", ""), (г.get("tehprocess") or г.get("fraza") or "")[:300])
    к["division"] = "kc"; к["division_badge"] = "КЦ (газ)"
    д["company"] = к; n += 1
    if "--primenit" in sys.argv:
        c.execute("UPDATE confirm_reviews SET panel_json=? WHERE id=? AND status='pending'", (json.dumps(д, ensure_ascii=False), кид))
if "--primenit" in sys.argv: c.commit()
print("%s: %d" % ("исправлено" if "--primenit" in sys.argv else "к исправлению", n))
