# -*- coding: utf-8 -*-
"""Какая доля отбивок у каждого почтовика — цена слепой отправки.

На mail.ru проба слепа: домен принимает любой RCPT, вердикт «принимает
всё» стоит у 2408 адресов из 2448. Значит вопрос не «проверять или нет»,
а «сколько стоит писать вслепую». Считаем отбивки на отправленные.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

отправлено = Counter()
for r in c.execute(
        "SELECT COALESCE(rc.mx_provider,'—') mx, COUNT(*) n FROM messages m "
        "LEFT JOIN recipients rc ON rc.id=m.recipient_id "
        "WHERE m.status='sent' AND substr(m.updated_at,1,10) >= "
        "date('now','-7 day') GROUP BY mx"):
    отправлено[str(r["mx"])] = int(r["n"])

отбито = Counter()
for r in c.execute(
        "SELECT COALESCE(rc.mx_provider,'—') mx, COUNT(*) n FROM events e "
        "JOIN messages m ON m.id=e.message_id "
        "LEFT JOIN recipients rc ON rc.id=m.recipient_id "
        "WHERE e.event_type='bounce' AND substr(e.created_at,1,10) >= "
        "date('now','-7 day') GROUP BY mx"):
    отбито[str(r["mx"])] = int(r["n"])

print(f"{'почтовик':<10} {'отправлено':>11} {'отбилось':>9} {'доля':>8}")
for mx in sorted(set(отправлено) | set(отбито),
                 key=lambda x: -отправлено.get(x, 0)):
    о, б = отправлено.get(mx, 0), отбито.get(mx, 0)
    д = f"{100.0 * б / о:.1f}%" if о else "—"
    print(f"{mx:<10} {о:>11} {б:>9} {д:>8}")

всего_о, всего_б = sum(отправлено.values()), sum(отбито.values())
print(f"{'ИТОГО':<10} {всего_о:>11} {всего_б:>9} "
      f"{100.0 * всего_б / всего_о if всего_о else 0:>7.1f}%")
