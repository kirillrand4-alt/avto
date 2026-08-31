# -*- coding: utf-8 -*-
"""Какое определение сегмента даёт 11 670 и почему там мало «неизвестной».

Моя цифра 3846 не из requisites — сверка показала, что там всего 21 совпадение.
Значит расходимся не в источнике выручки, а в НАСЕЛЕНИИ, которое считаем.
Перебираем определения и смотрим, где выручка известна.
"""
import json
import sqlite3

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
e.row_factory = sqlite3.Row


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


мейер = {}
for r in e.execute("SELECT inn, revenue_rub, site, cand_site, best_email"
                   "  FROM companies WHERE division LIKE '%meyer%'"):
    мейер[цифры(r["inn"])] = dict(r)
с_паспортом, непустой = set(), set()
for r in e.execute("SELECT inn, facts_json FROM site_facts"):
    и = цифры(r["inn"])
    с_паспортом.add(и)
    try:
        d = json.loads(r["facts_json"] or "{}") or {}
    except Exception:                                         # noqa: BLE001
        d = {}
    if any((len(v) if isinstance(v, (list, tuple, dict)) else bool(str(v).strip()))
           for v in d.values()):
        непустой.add(и)
с_почтой = {цифры(r[0]) for r in e.execute(
    "SELECT DISTINCT inn FROM emails WHERE email LIKE '%@%'")}
e.close()


def доля(множество, метка):
    если = [и for и in множество if и in мейер]
    нет = [и for и in если
           if мейер[и]["revenue_rub"] is None
           or int(мейер[и]["revenue_rub"] or 0) == 0]
    print("   %-42s %7d, выручка неизвестна %6d (%.1f%%)"
          % (метка, len(если), len(нет),
             100.0 * len(нет) / len(если) if если else 0))


все = set(мейер)
print("=== ОПРЕДЕЛЕНИЯ СЕГМЕНТА И ДОЛЯ НЕИЗВЕСТНОЙ ВЫРУЧКИ ===")
доля(все, "все division LIKE %meyer%")
доля({и for и in все if str(мейер[и]["site"] or "").strip()},
     "+ есть сайт")
доля(все & с_паспортом, "+ есть карточка site_facts")
доля(все & непустой, "+ паспорт непустой")
доля(все & с_почтой, "+ есть почта в emails")
доля(все & непустой & с_почтой, "+ паспорт непустой И почта")
доля({и for и in все & непустой & с_почтой
      if str(мейер[и]["site"] or "").strip()},
     "+ паспорт непустой, почта и сайт")

print("\n=== ПРОВЕРКА: СВЯЗАНА ЛИ ВЫРУЧКА С НАЛИЧИЕМ САЙТА ===")
с_сайтом = [и for и in все if str(мейер[и]["site"] or "").strip()]
без_сайта = [и for и in все if not str(мейер[и]["site"] or "").strip()]
for имя, гр in (("с сайтом", с_сайтом), ("без сайта", без_сайта)):
    нет = sum(1 for и in гр if мейер[и]["revenue_rub"] is None
              or int(мейер[и]["revenue_rub"] or 0) == 0)
    print("   %-10s %7d компаний, выручка неизвестна %6d (%.1f%%)"
          % (имя, len(гр), нет, 100.0 * нет / len(гр) if гр else 0))

print("\n=== ИТОГ ===")
print("если у компаний с сайтом и паспортом выручка почти всегда известна,")
print("то мы оба правы, но про РАЗНЫЕ множества: она считает уже отобранных,")
print("я — весь сегмент до отбора.")
