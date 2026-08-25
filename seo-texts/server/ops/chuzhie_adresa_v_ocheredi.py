# -*- coding: utf-8 -*-
"""Сколько в очереди адресов, которые компании не принадлежат.

nalog-k@bk.ru ушёл как «Автобан», а ответила «Налоговая Консультация»: в
базе обзвона у компаний нередко записан адрес бухгалтера, аудитора или
юриста, который сдаёт за них отчётность. Считаем, сколько такого в очереди
и откуда эти адреса взялись.
"""
import re
import sqlite3
from collections import Counter

ЧУЖИЕ = re.compile(
    r"^(nalog|nalogi|buh|buch|buhgalter|audit|konsult|consult|jurist|urist|"
    r"pravo|otchet|report|1c|odinc|dekl)", re.I)

s = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
s.row_factory = sqlite3.Row
очередь = s.execute(
    "SELECT r.id, r.email, r.company_name, r.inn FROM messages m "
    "  JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status IN ('scheduled','sending')").fetchall()
print("писем в очереди: %d" % len(очередь))

e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
e.row_factory = sqlite3.Row
источник = {}
for р in e.execute("SELECT email, source, role, addr_class FROM emails"):
    источник[(р["email"] or "").strip().lower()] = (
        р["source"] or "?", р["role"] or "", р["addr_class"] or "")

по_источнику = Counter()
подозрительные = []
for р in очередь:
    а = (р["email"] or "").strip().lower()
    ист = источник.get(а, ("нет в обогащении", "", ""))
    по_источнику[ист[0]] += 1
    лок = а.split("@")[0]
    if ЧУЖИЕ.match(лок):
        подозрительные.append((р, ист))

print("\n=== ОТКУДА АДРЕСА ОЧЕРЕДИ ===")
for к, н in по_источнику.most_common():
    print("   %-28s %5d" % (к, н))

print("\n=== ПОХОЖИ НА БУХГАЛТЕРА/АУДИТОРА: %d ===" % len(подозрительные))
for р, ист in подозрительные[:20]:
    print("   %-30s %-34s ИНН %s | %s"
          % (р["email"][:30], str(р["company_name"] or "")[:34], р["inn"], ист[0]))

# то же по всей базе рассылки, чтобы понимать масштаб на будущее
всего = 0
for р in s.execute("SELECT email FROM recipients"):
    if ЧУЖИЕ.match((р["email"] or "").split("@")[0].lower()):
        всего += 1
print("\nтаких адресов во всей базе рассылки: %d" % всего)
