# -*- coding: utf-8 -*-
"""Сколько писем ждёт отправки и у скольких вердикт вынес РАБОТНИК.

Справка соседней сессии (PROBA-ADRESA-PERED-OCHEREDYU.md) уточняет два
момента, которые меняют счёт:
  * addr_probe.ts — время последнего импорта, а не время пробы; по нему
    судить о свежести нельзя;
  * вердикт в addr_probe может быть и не от работника: отбивка настоящего
    письма пишет туда же с source='hard-bounce'.
Поэтому «проверен работником» считаем по source, а не по факту строки.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

ряды = c.execute(
    "SELECT m.status mst, cr.email, COALESCE(p.verdict,'') v, "
    "       COALESCE(p.source,'') src, COALESCE(rc.mx_provider,'') mx "
    "FROM messages m "
    "JOIN confirm_reviews cr ON cr.message_id = m.id "
    "LEFT JOIN recipients rc ON rc.id = m.recipient_id "
    "LEFT JOIN addr_probe p ON p.email = lower(cr.email) "
    "WHERE cr.status IN ('approved','edited') "
    "AND m.status IN ('scheduled','sending')").fetchall()

print(f"ЖДУТ ОТПРАВКИ: {len(ряды)}  "
      f"({dict(Counter(r['mst'] for r in ряды))})")

по_ист = Counter(str(r["src"] or "нет строки") for r in ряды)
print("\nоткуда вердикт:")
for k, n in по_ист.most_common():
    print(f"  {n:>4}  {k}")

print("\nвердикт × источник:")
пары = Counter((str(r["v"] or "нет"), str(r["src"] or "нет строки"))
               for r in ряды)
for (v, s), n in пары.most_common():
    print(f"  {n:>4}  {v:<16} {s}")

# То, что владелец и спрашивает: подтверждённых живыми работником.
живых = sum(1 for r in ряды if str(r["v"]) == "есть"
            and str(r["src"] or "").lower() not in ("hard-bounce", ""))
слепых = sum(1 for r in ряды if str(r["v"]) == "принимает всё")
print(f"\nработник подтвердил ящик («есть»): {живых}")
print(f"работник ответил «принимает всё» (узнать нельзя): {слепых}")
