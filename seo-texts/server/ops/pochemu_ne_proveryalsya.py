# -*- coding: utf-8 -*-
"""Почему адрес из очереди не проверен: жив ли работник проб и что он успел."""
import os
import sqlite3
import time

АДРЕС = "ogneborets19@mail.ru"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

print("=== таблица addr_probe ===")
try:
    всего = c.execute("SELECT COUNT(*) FROM addr_probe").fetchone()[0]
    print("   строк: %d" % всего)
    for r in c.execute("SELECT verdict, COUNT(*) n FROM addr_probe "
                       "GROUP BY verdict ORDER BY n DESC"):
        print("   %-22s %d" % (r["verdict"], r["n"]))
    посл = c.execute("SELECT MAX(ts) FROM addr_probe").fetchone()[0]
    print("   последняя проба: %s" % посл)
    for r in c.execute("SELECT substr(ts,1,10) д, COUNT(*) n FROM addr_probe "
                       "GROUP BY д ORDER BY д DESC LIMIT 6"):
        print("      %s  %d" % (r["д"], r["n"]))
except Exception as ex:                                       # noqa: BLE001
    print("   не прочлась: %s" % ex)

print("")
print("=== этот адрес ===")
r = c.execute("SELECT * FROM addr_probe WHERE email=?", (АДРЕС,)).fetchone()
print("   в addr_probe: %s" % (dict(r) if r else "НЕТ"))
rec = c.execute("SELECT id, email, company_name, inn FROM recipients "
                "WHERE email=?", (АДРЕС,)).fetchone()
print("   получатель: %s" % (dict(rec) if rec else "нет"))
if rec:
    for cr in c.execute("SELECT id, status, created_at FROM confirm_reviews "
                        "WHERE recipient_id=? ORDER BY id DESC LIMIT 3",
                        (rec["id"],)):
        print("   карточка #%s %s %s" % (cr["id"], cr["status"], cr["created_at"]))

print("")
print("=== покрытие пробами очереди pending ===")
q = c.execute(
    "SELECT COUNT(*) n, SUM(CASE WHEN p.email IS NULL THEN 1 ELSE 0 END) без "
    "  FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN addr_probe p ON p.email=r.email "
    " WHERE cr.status='pending'").fetchone()
print("   pending карточек с получателем: %s, из них без пробы: %s"
      % (q["n"], q["без"]))
c.close()

print("")
print("=== файлы работника проб ===")
for п in (r"C:\sender\_ops\probe-zadanie.jsonl", r"C:\sender\_ops\probe-rezultat.jsonl",
          r"C:\sender\_ops\lyogkaya-progress.json"):
    if os.path.exists(п):
        print("   %-46s %8d б  %s" % (os.path.basename(п), os.path.getsize(п),
                                      time.strftime("%d.%m %H:%M",
                                                    time.localtime(os.path.getmtime(п)))))
    else:
        print("   %-46s НЕТ" % os.path.basename(п))
