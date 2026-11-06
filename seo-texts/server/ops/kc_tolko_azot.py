# -*- coding: utf-8 -*-
"""Письма КЦ-1 про азот/кислород: сколько без слова «компрессор»/«сжат» (только газ)."""
import collections, sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
сч = collections.Counter(); пр = []
for mid, st, s, b, d in c.execute("SELECT id, status, subject, body_rendered, substr(created_at,1,10) FROM messages WHERE campaign_id=17"):
    т = ((s or "") + " " + (b or "")).lower().replace("компрессор центр", "КЦ")
    газ = "азот" in т or "кислород" in т
    if not газ: continue
    воздух = "компрессор " in т.replace("компрессорн", "") or "сжат" in т or "компрессоры" in т or "компрессорами" in т
    сч[(st, "газ+воздух" if воздух else "ТОЛЬКО ГАЗ")] += 1
    if not воздух and len(пр) < 3: пр.append((mid, s))
for k, v in sorted(сч.items()): print(k, v)
print(пр)
