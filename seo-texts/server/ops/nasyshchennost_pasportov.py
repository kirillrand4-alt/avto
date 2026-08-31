# -*- coding: utf-8 -*-
"""Насколько паспорта сайта на самом деле наполнены.

Я считал len(facts_json) — это ЧИСЛО КЛЮЧЕЙ схемы, всегда 20, и оно не
говорит ни о чём. Правильная мера — сколько блоков НЕПУСТЫ.
"""
import json
import sqlite3
from collections import Counter

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row


def непустых(сырое):
    try:
        d = json.loads(сырое or "{}") or {}
    except Exception:                                         # noqa: BLE001
        return None
    if not isinstance(d, dict):
        return None
    n = 0
    for v in d.values():
        if isinstance(v, str):
            if v.strip():
                n += 1
        elif isinstance(v, (list, tuple, dict)):
            if len(v):
                n += 1
        elif v not in (None, 0, False):
            n += 1
    return n, len(d)


все, ключей = Counter(), Counter()
пустых, битых = 0, 0
по_инн = {}
for r in e.execute("SELECT inn, facts_json FROM site_facts"):
    рез = непустых(r["facts_json"])
    if рез is None:
        битых += 1
        continue
    n, k = рез
    все[n] += 1
    ключей[k] += 1
    по_инн["".join(c for c in str(r["inn"] or "") if c.isdigit())] = n
    if n == 0:
        пустых += 1

всего = sum(все.values())
def медиана(счёт):
    сп = sorted(x for n, c in счёт.items() for x in [n] * c)
    return сп[len(сп) // 2] if сп else 0


def процентиль(счёт, p):
    сп = sorted(x for n, c in счёт.items() for x in [n] * c)
    return сп[int(len(сп) * p)] if сп else 0


print("=== ПАСПОРТА В ОБОГАЩЕНИИ ===")
print("   всего карточек site_facts: %d (битых json: %d)" % (всего, битых))
print("   ключей в схеме: %s" % dict(ключей.most_common(4)))
print("   ПОЛНОСТЬЮ ПУСТЫХ (ноль непустых блоков): %d (%.1f%%)"
      % (пустых, 100.0 * пустых / всего if всего else 0))
print("   непустых блоков: медиана %d, 10%%–90%% %d–%d, максимум %d"
      % (медиана(все), процентиль(все, 0.1), процентиль(все, 0.9),
         max(все) if все else 0))
print("\n   распределение (сколько карточек с N непустыми блоками):")
for n in sorted(все)[:14]:
    print("      %2d блоков  %6d" % (n, все[n]))
e.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
s.row_factory = sqlite3.Row
партия = Counter()
без = 0
for r in s.execute("SELECT DISTINCT inn FROM confirm_reviews"
                   " WHERE campaign_id=11 AND created_at >= '2026-08-31'"
                   "   AND inn IS NOT NULL"):
    и = "".join(c for c in str(r[0] or "") if c.isdigit())
    if и in по_инн:
        партия[по_инн[и]] += 1
    else:
        без += 1
s.close()
print("\n=== ПАСПОРТА КОМПАНИЙ СЕГОДНЯШНЕЙ ПАРТИИ ===")
print("   компаний с паспортом: %d, без паспорта: %d" % (sum(партия.values()), без))
print("   непустых блоков: медиана %d, 10%%–90%% %d–%d"
      % (медиана(партия), процентиль(партия, 0.1), процентиль(партия, 0.9)))
print("   пустых паспортов в партии: %d" % партия.get(0, 0))
print("\n   распределение по партии:")
for n in sorted(партия):
    print("      %2d блоков  %4d" % (n, партия[n]))

print("\n=== ИТОГ ===")
print("«20 полей» — это размер схемы, он одинаков у всех и ничего не значит.")
print("Содержательная мера — непустые блоки: по базе медиана %d, по партии %d."
      % (медиана(все), медиана(партия)))
