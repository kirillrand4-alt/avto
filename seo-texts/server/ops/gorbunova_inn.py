# -*- coding: utf-8 -*-
import sqlite3
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
e.row_factory = sqlite3.Row
print("=== обогащение: строки по этим адресам ===")
for r in e.execute("SELECT inn, email, role, person, probe_verdict, source "
                   "  FROM emails WHERE email IN "
                   "  ('m.gorbunova@incab.ru','sales@incab.ru','chizhanov@incab.ru',"
                   "   'burenkov@incab.ru','toropov@incab.ru')"):
    print("   ИНН %-13s %-28s роль %-20s %s"
          % (r["inn"], r["email"], str(r["role"])[:20], str(r["person"] or "")[:20]))
e.close()
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
s.row_factory = sqlite3.Row
print("")
print("=== база рассылки: строка Горбуновой ===")
for r in s.execute("SELECT id, email, inn, company_name, source, created_at "
                   "  FROM recipients WHERE email='m.gorbunova@incab.ru'"):
    print("   rid %s | ИНН %s | %s | источник %s | %s"
          % (r["id"], r["inn"], str(r["company_name"])[:34], r["source"],
             str(r["created_at"])[:16]))
print("")
print("=== писали ли ей вообще ===")
for r in s.execute("SELECT m.id, m.status, m.sent_at, m.last_error FROM messages m "
                   "  JOIN recipients rc ON rc.id=m.recipient_id "
                   " WHERE rc.email='m.gorbunova@incab.ru'"):
    print("   msg %s %s %s | %s" % (r["id"], r["status"], str(r["sent_at"])[:16],
                                    str(r["last_error"] or "")[:70]))
s.close()
