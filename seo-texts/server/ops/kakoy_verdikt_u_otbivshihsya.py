# -*- coding: utf-8 -*-
"""Какой вердикт пробы стоял у отбившихся адресов и чем отличается день.

Проверены все 100% - значит дело не в «не проверяли», а в ТОМ, ЧТО проба
ответила. «Принимает всё» - это домен, который на пробу отвечает «да»
кому угодно: несуществующий ящик там виден только по отбивке. Смотрим
раскладку вердиктов у отбившихся и по дням отправки.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
проба = {str(р["email"]).lower(): str(р["verdict"] or "")
         for р in c.execute("SELECT email, verdict FROM addr_probe")
         if р["email"]}

отб = c.execute(
    "SELECT r.email, substr(COALESCE(e.event_ts,e.created_at),1,10) день "
    "  FROM events e JOIN recipients r ON r.id=e.recipient_id "
    " WHERE e.event_type='bounce' "
    "   AND substr(COALESCE(e.event_ts,e.created_at),1,10) >= '2026-08-17'"
).fetchall()
print("вердикт пробы у ОТБИВШИХСЯ:")
for в, н in Counter(проба.get(str(р["email"]).lower(), "нет вердикта")
                    for р in отб).most_common():
    print(f"  {н:>3}  {в}")
print("\nпоимённо (сегодня):")
for р in отб:
    if р["день"] == "2026-08-21":
        print(f"  {р['email']:<34} {проба.get(str(р['email']).lower(),'-')}")

ряды = c.execute(
    "SELECT substr(COALESCE(m.sent_at,m.updated_at),1,10) день, r.email "
    "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent' "
    "   AND substr(COALESCE(m.sent_at,m.updated_at),1,10) >= '2026-08-17'"
).fetchall()
по_дням = {}
for р in ряды:
    по_дням.setdefault(р["день"], Counter())[
        проба.get(str(р["email"]).lower(), "нет вердикта")] += 1
print(f"\n{'день':<12} {'всего':>6} {'принимает всё':>15} {'есть':>7} "
      f"{'прочее':>8} {'доля catch-all':>15}")
for д in sorted(по_дням):
    сч = по_дням[д]
    всего = sum(сч.values())
    ка = сч.get("принимает всё", 0)
    ес = сч.get("есть", 0)
    print(f"{д:<12} {всего:>6} {ка:>15} {ес:>7} {всего-ка-ес:>8} "
          f"{(100.0*ка/всего if всего else 0):>14.1f}%")
    прочее = {к: v for к, v in сч.items() if к not in ("принимает всё", "есть")}
    if прочее:
        print(f"             прочее: {прочее}")
