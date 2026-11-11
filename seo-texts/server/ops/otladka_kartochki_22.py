# -*- coding: utf-8 -*-
"""Отладка карточек кампании 22: причина снятия, фраза, компания по списку id. Только чтение.  otladka_kartochki_22.py id,id,..."""
import json, sqlite3, sys
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=60)
for кид in [int(x) for x in sys.argv[1].split(",")]:
    r = c.execute("SELECT status, reason, COALESCE(edited_body, body), panel_json FROM confirm_reviews WHERE id=?", (кид,)).fetchone()
    комп = (json.loads(r[3] or "{}").get("company") or {})
    print("#%d %s | %s | %s\n   фраза: %s\n   причина: %s" % (кид, r[0], (комп.get("name") or "")[:40], (комп.get("activity") or "")[:90],
          (r[2] or "").split("\n\n")[1][:170], (r[1] or "")[:150]))
