# -*- coding: utf-8 -*-
"""Сколько компаний получили сегодня больше одной копии."""
import re
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
по_инн = defaultdict(list)
for r in c.execute(
        "SELECT rc.inn, rc.email, m.sent_at, m.status FROM messages m "
        "  JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE m.status='sent' AND substr(m.sent_at,1,10)=date('now')"):
    по_инн[str(r["inn"] or "")].append((str(r["sent_at"])[:19], r["email"]))
дубли = {и: v for и, v in по_инн.items() if и and len(v) > 1}
print("отправлено сегодня: %d писем, компаний: %d"
      % (sum(len(v) for v in по_инн.values()), len(по_инн)))
print("компаний с 2+ письмами СЕГОДНЯ: %d" % len(дубли))
for и, v in list(дубли.items())[:8]:
    print("   ИНН %-13s %s" % (и, " | ".join("%s %s" % (t[11:16], e) for t, e in v)))

# сколько ещё стоит в расписании к компаниям, которым сегодня уже ушло
ждут = defaultdict(int)
for r in c.execute(
        "SELECT rc.inn, COUNT(*) n FROM messages m "
        "  JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE m.status IN ('scheduled','sending') GROUP BY 1"):
    ждут[str(r["inn"] or "")] = r["n"]
рискуют = {и: ждут[и] for и in по_инн if ждут.get(и)}
print("")
print("компаний, которым СЕГОДНЯ уже ушло и ещё стоит в расписании: %d "
      "(писем в очереди: %d)" % (len(рискуют), sum(рискуют.values())))

# транслитерационные близнецы: secretar vs sekretar
пары = 0
примеры = []
for и, v in по_инн.items():
    лок = [e.split("@")[0].lower() for _t, e in v]
    for x in range(len(лок)):
        for y in range(x + 1, len(лок)):
            a, b = лок[x], лок[y]
            if a != b and a.replace("k", "c") == b.replace("k", "c"):
                пары += 1
                if len(примеры) < 5:
                    примеры.append((и, v[x][1], v[y][1]))
print("")
print("=== близнецы по транслитерации (k/c) среди сегодняшних ===")
print("пар: %d" % пары)
for и, a, b in примеры:
    print("   ИНН %-13s %s  и  %s" % (и, a, b))
c.close()
