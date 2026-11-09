# -*- coding: utf-8 -*-
"""Все поля карточки (кроме тела) + события с её id: kartochka_vsya.py ID [ID…]. Только чтение."""
import json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90); c.row_factory = sqlite3.Row
for i in sys.argv[1:]:
    r = c.execute("SELECT * FROM confirm_reviews WHERE id=?", (int(i),)).fetchone()
    print("== #%s" % i)
    for k in r.keys():
        if k == "body": continue
        v = r[k]
        if k == "panel_json" and v:
            try: v = {kk: (str(vv)[:150]) for kk, vv in json.loads(v).items()}
            except Exception: v = str(v)[:600]
        print("  %s: %s" % (k, v))
    шк = [x[1] for x in c.execute("PRAGMA table_info(events)")]
    for e in c.execute("SELECT * FROM events WHERE CAST(%s AS TEXT) LIKE ? ORDER BY 1 LIMIT 30" % ("payload_json" if "payload_json" in шк else шк[-1]), ("%%%s%%" % i,)):
        print("  EV", tuple(e)[:6])
