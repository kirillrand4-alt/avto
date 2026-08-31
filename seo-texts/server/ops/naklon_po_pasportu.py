# -*- coding: utf-8 -*-
"""Отдача ночного блока в разрезе наполненности паспорта — тот самый наклон."""
import glob
import io
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб",
        "мощности")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def мера(сырое):
    try:
        d = json.loads(сырое or "{}") or {}
    except Exception:                                         # noqa: BLE001
        return 0
    n = 0
    for к in ПОЛЯ:
        v = d.get(к)
        if isinstance(v, str):
            v = [v] if v.strip() else []
        if isinstance(v, (list, tuple)) and len(v):
            n += 1
    return n


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
поля = {}
for r in e.execute("SELECT inn, facts_json FROM site_facts"):
    поля[цифры(r[0])] = мера(r[1])
e.close()

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
свод = defaultdict(Counter)
деньги = defaultdict(float)
причины = Counter()
with io.open(ЖУРНАЛ, encoding="utf-8") as f:
    строки = f.readlines()
for с in строки[-8000:]:
    try:
        z = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    if z.get("этап") != "итог" or z.get("день") != "2026-08-31":
        continue
    if str(z.get("модель") or "") != "claude-sonnet-4-6":
        continue
    и = цифры(z.get("inn"))
    б = поля.get(и, -1)
    ключ = "нет паспорта" if б < 0 else ("%d полей" % б)
    свод[ключ]["ок" if z.get("ок") else "брак"] += 1
    ц = z.get("цена_$")
    if isinstance(ц, (int, float)):
        деньги[ключ] += float(ц)
    if not z.get("ок"):
        причины[str(z.get("брак"))[:60]] += 1

print("=== ОТДАЧА ПО НАПОЛНЕННОСТИ ПАСПОРТА (ночной блок, соннет) ===")
print("   %-14s %7s %7s %8s %12s %12s"
      % ("уровень", "всего", "ок", "отдача", "потрачено", "за письмо"))
порядок = sorted(свод, key=lambda к: (-1 if к == "нет паспорта"
                                      else int(к.split()[0])))
итого = Counter()
for к in порядок:
    n = sum(свод[к].values())
    ок = свод[к]["ок"]
    итого.update(свод[к])
    print("   %-14s %7d %7d %7.0f%% %11.2f$ %11s"
          % (к, n, ок, 100.0 * ок / n if n else 0, деньги[к],
             ("%.3f$" % (деньги[к] / ок)) if ок else "—"))
в = sum(итого.values())
print("   %-14s %7d %7d %7.0f%% %11.2f$ %11.3f$"
      % ("ИТОГО", в, итого["ок"], 100.0 * итого["ок"] / в if в else 0,
         sum(деньги.values()),
         sum(деньги.values()) / итого["ок"] if итого["ок"] else 0))

print("\n=== ПРИЧИНЫ БРАКА ===")
for п, n in причины.most_common(8):
    print("   %4d  %s" % (n, п))
