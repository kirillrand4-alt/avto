# -*- coding: utf-8 -*-
"""Сколько отбивок — это ВТОРОЙ промах по одной и той же компании."""
import sqlite3
from collections import defaultdict
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
ПУБЛИЧНЫЕ = {"mail.ru", "bk.ru", "inbox.ru", "list.ru", "yandex.ru", "ya.ru",
             "gmail.com", "rambler.ru", "internet.ru", "mail.com"}
по_инн, по_домену, по_адресу = defaultdict(list), defaultdict(set), defaultdict(int)
всего = 0
for r in c.execute(
        "SELECT e.event_ts, r.email, r.inn, r.company_name FROM events e "
        "  LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND e.event_ts >= '2026-08-22'"):
    почта = str(r["email"] or "").lower()
    if "@" not in почта:
        continue
    всего += 1
    домен = почта.split("@")[-1]
    по_адресу[почта] += 1
    инн = "".join(x for x in str(r["inn"] or "") if x.isdigit())
    if инн:
        по_инн[инн].append((почта, str(r["event_ts"])[:10],
                            str(r["company_name"] or "")[:34]))
    if домен not in ПУБЛИЧНЫЕ:
        по_домену[домен].add(почта)
print("отбивок за неделю (с 22.08): %d" % всего)
повтор_инн = {и: v for и, v in по_инн.items() if len(v) > 1}
print("\nкомпаний, где отбилось больше одного письма: %d" % len(повтор_инn
      if False else повтор_инн))
лишних = sum(len(v) - 1 for v in повтор_инн.values())
print("отбивок-повторов по компании (второй и далее промах): %d" % лишних)
for инн, v in sorted(повтор_инн.items(), key=lambda x: -len(x[1])):
    адреса = {а for а, _, _ in v}
    print("  ИНН %-12s %-34s писем отбилось %d, разных адресов %d"
          % (инн, v[0][2], len(v), len(адреса)))
    for а, д, _ in v:
        print("        %-34s %s" % (а, д))
повтор_адрес = {а: n for а, n in по_адресу.items() if n > 1}
print("\nадресов, отбившихся дважды и более: %d" % len(повтор_адрес))
for а, n in sorted(повтор_адрес.items(), key=lambda x: -x[1]):
    print("  %-36s %d" % (а, n))
корп = {д: v for д, v in по_домену.items() if len(v) > 1}
print("\nкорпоративных доменов с двумя и более РАЗНЫМИ мёртвыми адресами: %d"
      % len(корп))
for д, v in sorted(корп.items(), key=lambda x: -len(x[1])):
    print("  %-26s %s" % (д, ", ".join(sorted(v))))
c.close()
