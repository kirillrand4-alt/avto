# -*- coding: utf-8 -*-
"""Чем заняты карточки, на которые наткнулись заходы A/B (статус/причина)."""
import collections, io, json, sqlite3
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
к = [json.loads(s)["karta"] for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")
     if '"напоминания' in s or True]
зап = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-pilot.jsonl", encoding="utf-8")]
ид = [з.get("karta") for з in зап[-200:] if з.get("karta")]
сч = collections.Counter()
for i in ид:
    р = c.execute("SELECT status, reason, substr(panel_json,1,120) FROM confirm_reviews WHERE id=?", (i,)).fetchone()
    сч[(р[0], (р[1] or "")[:60], "заходы" if р and "заходы" in (р[2] or "") else ("v2" if р and "v2" in (р[2] or "") else (р[2] or "")[:50]))] += 1
for к_, н in сч.most_common(15):
    print(н, к_)
