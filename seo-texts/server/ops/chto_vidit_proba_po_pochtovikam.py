# -*- coding: utf-8 -*-
"""Что проба вообще способна увидеть у каждого почтовика.

Все 423 письма в отправке имеют вердикт пробы — и всё же шесть отбились
с «550 invalid mailbox». Значит вердикт был не «нет ящика», а такой, что
ничего не гарантирует. Смотрим разрез: какой вердикт проба выносит на
каком почтовике.
"""
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

# Вердикты пробы в разрезе почтовика получателя.
по = defaultdict(Counter)
for r in c.execute(
        "SELECT COALESCE(rc.mx_provider,'—') mx, p.verdict v "
        "FROM addr_probe p LEFT JOIN recipients rc "
        "ON lower(rc.email)=p.email WHERE p.verdict IS NOT NULL"):
    по[str(r["mx"])][str(r["v"])] += 1

print(f"{'почтовик':<12} " + "  ".join(f"{k:>14}" for k in
      ("есть", "нет ящика", "принимает всё", "неясно", "нет MX")))
for mx, счёт in sorted(по.items(), key=lambda x: -sum(x[1].values()))[:8]:
    строка = "  ".join(f"{счёт.get(k, 0):>14}" for k in
                       ("есть", "нет ящика", "принимает всё", "неясно", "нет MX"))
    print(f"{mx:<12} {строка}")

# Что стоит у отбившихся адресов и что стояло в очереди на отправку.
print("\n== отбившиеся сегодня ==")
for r in c.execute(
        "SELECT r.email, COALESCE(rc.mx_provider,'') mx, "
        "       COALESCE(p.verdict,'') v, p.ts "
        "FROM events e JOIN messages m ON m.id=e.message_id "
        "JOIN recipients rc ON rc.id=m.recipient_id "
        "JOIN confirm_reviews r ON r.message_id=m.id "
        "LEFT JOIN addr_probe p ON p.email=lower(r.email) "
        "WHERE e.event_type='bounce' "
        "AND substr(e.created_at,1,10)=date('now') LIMIT 12"):
    print(f"  {str(r['email']):<34} mx={r['mx']:<8} вердикт сейчас: {r['v']}")

# Сколько писем в отправке идёт на «принимает всё» — то есть вслепую.
print("\n== письма в отправке по вердикту и почтовику ==")
св = defaultdict(Counter)
for r in c.execute(
        "SELECT COALESCE(rc.mx_provider,'—') mx, COALESCE(p.verdict,'нет') v "
        "FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
        "LEFT JOIN recipients rc ON rc.id=m.recipient_id "
        "LEFT JOIN addr_probe p ON p.email=lower(cr.email) "
        "WHERE cr.status IN ('approved','edited') "
        "AND m.status IN ('scheduled','sending')"):
    св[str(r["mx"])][str(r["v"])] += 1
for mx, счёт in sorted(св.items(), key=lambda x: -sum(x[1].values())):
    print(f"  {mx:<10} {dict(счёт)}")
