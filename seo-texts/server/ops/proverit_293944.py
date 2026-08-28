# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT id, recipient_id, event_type FROM events WHERE id=293944").fetchone()
print("событие 293944: получатель=%s тип=%s" % (r["recipient_id"], r["event_type"]))
l = c.execute("SELECT id, status, email, reply_kind, created_at FROM leads "
              " WHERE recipient_id=30282").fetchone()
print("лид: %s" % (dict(l) if l else "нет"))
c.close()
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=30)
x = e.execute("SELECT email, person, source FROM emails "
              " WHERE email='pav4@virtex-food.ru'").fetchone()
print("преемник в обогащении: %s" % (list(x) if x else "нет"))
e.close()
