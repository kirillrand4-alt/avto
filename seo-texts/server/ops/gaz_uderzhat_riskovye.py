# -*- coding: utf-8 -*-
"""Удержать на ручном подтверждении карточки кампании 22 с рискованным вердиктом пробы: «неясно» с «MX не найден»
или «getaddrinfo failed» (домен без почты/не резолвится). Ставит actions.confirm_hold=True и стоп-флаг — vse_v_avto
их пропустит. Текст не трогаем.  gaz_uderzhat_riskovye.py [--primenit]"""
import json, re, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
вер = {em: (v, a) for em, v, a in c.execute("SELECT lower(email), verdict, COALESCE(answer,'') FROM addr_probe")}
n = 0
for кид, em, pj in c.execute("SELECT id, lower(email), panel_json FROM confirm_reviews WHERE campaign_id=22 AND status='pending'").fetchall():
    v, a = вер.get(em, ("", ""))
    if not (v == "неясно" and re.search(r"MX не найден|getaddrinfo", a)): continue
    д = json.loads(pj or "{}")
    д.setdefault("actions", {})["confirm_hold"] = True
    д["stop_flags"] = list(д.get("stop_flags") or []) + [{"code": "proba_mx", "label": "проба: %s" % a[:80], "severity": "red"}]
    n += 1
    if "--primenit" in sys.argv:
        c.execute("UPDATE confirm_reviews SET panel_json=? WHERE id=? AND status='pending'", (json.dumps(д, ensure_ascii=False), кид))
if "--primenit" in sys.argv: c.commit()
print("%s: %d" % ("удержано" if "--primenit" in sys.argv else "к удержанию", n))
