# -*- coding: utf-8 -*-
"""Только чтение: кому мы писали больше одного раза. Время в базе — UTC."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

print("=== ОДИН И ТОТ ЖЕ АДРЕС ДВАЖДЫ (всё время) ===")
ряды = list(c.execute(
    "SELECT r.email, COUNT(*) k, MIN(m.sent_at) п, MAX(m.sent_at) о"
    " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.status='sent' GROUP BY r.email HAVING k>1 ORDER BY k DESC"))
print("  адресов: %d" % len(ряды))
for р in ряды[:10]:
    print("  %-36s %d писем, %s .. %s"
          % (р["email"][:36], р["k"], str(р["п"])[:10], str(р["о"])[:10]))

print("\n=== ОДНА КОМПАНИЯ (ИНН) НЕСКОЛЬКО РАЗ ===")
for окно, подпись in ((7, "за 7 дней"), (14, "за 14 дней"), (999, "всё время")):
    гр = (utc - dt.timedelta(days=окно)).isoformat()
    ряды = list(c.execute(
        "SELECT r.inn, COUNT(*) k FROM messages m JOIN recipients r"
        " ON r.id=m.recipient_id WHERE m.status='sent' AND m.sent_at>=?"
        " AND r.inn IS NOT NULL AND r.inn<>'' GROUP BY r.inn HAVING k>1", (гр,)))
    писем = sum(р["k"] for р in ряды)
    print("  %-12s компаний с 2+ письмами: %4d (писем в них %d)"
          % (подпись, len(ряды), писем))

print("\n=== ХУДШИЕ СЛУЧАИ ЗА 14 ДНЕЙ ===")
гр = (utc - dt.timedelta(days=14)).isoformat()
for р in c.execute(
        "SELECT r.inn, r.company_name, COUNT(*) k, GROUP_CONCAT(DISTINCT r.email) поч"
        " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.status='sent' AND m.sent_at>=? AND r.inn IS NOT NULL AND r.inn<>''"
        " GROUP BY r.inn HAVING k>2 ORDER BY k DESC LIMIT 12", (гр,)):
    print("  %-12s %-26s %d писем" % (р["inn"], str(р["company_name"])[:26], р["k"]))
    print("      %s" % str(р["поч"])[:100])

print("\n=== ЧТО ДАЛА МОЯ СЕГОДНЯШНЯЯ ПРАВКА ===")
утро = utc.replace(hour=0, minute=0, second=0).isoformat()
ряды = list(c.execute(
    "SELECT r.inn, r.company_name, r.email FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.status='sent' AND m.sent_at>=? AND m.campaign_id=12"
    " AND r.inn IS NOT NULL AND r.inn<>''", (утро,)))
повторно = []
for р in ряды:
    n = c.execute("SELECT COUNT(*) FROM messages m2 JOIN recipients r2"
                  " ON r2.id=m2.recipient_id WHERE m2.status='sent'"
                  " AND m2.campaign_id<>12 AND r2.inn=? AND m2.sent_at>=?",
                  (р["inn"], (utc - dt.timedelta(days=21)).isoformat())).fetchone()[0]
    if n:
        повторно.append((р["company_name"], р["email"], n))
print("  писем партии вебинара в компании, которым писали за 3 недели: %d"
      % len(повторно))
for н, е, n in повторно[:14]:
    print("    %-26s %-30s (до этого %d писем)" % (str(н)[:26], е[:30], n))
