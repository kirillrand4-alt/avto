# -*- coding: utf-8 -*-
"""Только чтение: откуда берутся вердикты addr_probe и что в очереди."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== addr_probe: ИСТОЧНИК ВЕРДИКТА ===")
for р in s.execute("SELECT source, verdict, COUNT(*) n FROM addr_probe"
                   " GROUP BY source, verdict ORDER BY n DESC LIMIT 16"):
    print("  %-22s %-24s %6d" % (str(р["source"])[:22], str(р["verdict"])[:24], р["n"]))

print("\n=== ОЧЕРЕДЬ: ЧЕМ ПРОВЕРЕНЫ АДРЕСА ===")
c = Counter()
for р in s.execute("SELECT COALESCE(ap.source,'(пробы нет)') src,"
                   " COALESCE(ap.verdict,'-') v, COUNT(*) n"
                   " FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " LEFT JOIN addr_probe ap ON lower(ap.email)=lower(r.email)"
                   " WHERE m.status='scheduled' GROUP BY src, v ORDER BY n DESC"):
    print("  %-24s %-22s %5d" % (str(р["src"])[:24], str(р["v"])[:22], р["n"]))
    c[str(р["src"])] += р["n"]

print("\n=== ИТОГ ===")
всего = sum(c.values())
реал = sum(v for k, v in c.items() if k not in ("(пробы нет)", "hard-bounce"))
print("  в очереди: %d" % всего)
print("  с НАСТОЯЩЕЙ пробой (не из отбивки): %d (%.0f%%)"
      % (реал, 100.0 * реал / max(1, всего)))
print("  доля отбивок сегодня: 9 на 259 отправок = 3.5%%")
print("  для сравнения: 25.08 2.6%%, 26.08 2.6%%, 27.08 2.3%%, 28.08 3.9%%, 31.08 3.1%%")
n = s.execute("SELECT COUNT(*) n FROM messages WHERE status='scheduled'").fetchone()["n"]
print("  в очереди сейчас: %d" % n)
