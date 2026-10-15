# -*- coding: utf-8 -*-
"""Вернуть в работу КЦ компании группы «КЦ тест», которых линза покупателя
сняла «НЕ ПОКУПАТЕЛЬ» по отрасли до правки 15.10 («почему не покупатели
заводы?»). Из журнала gen-kc-test.jsonl: итог с браком «НЕ ПОКУПАТЕЛЬ», кроме
«переставить на meyer» и кроме тех, кто сам делает компрессоры/пневматику/газы.
Вердикт обогащения -> «кц», источник «владелец 15.10» (старше линзы), журнал
_ops/vernut-ne-pokupateley-kc.jsonl. Генерация возьмёт их заново.

    vernut_ne_pokupateley_kc.py [--primenit]
"""
import io
import json
import os
import re
import sqlite3
import sys
import time

ПРИМ = "--primenit" in sys.argv
САМИ = re.compile(r"(?i)компрессор|пневм|промышленн\w+ газ|воздухоразделит|торгу|торговый дом|торговая компан|"
                  r"ремонт квартир|научные исследования|транспортирует и реализует газ|проектирование и строительство")
итог = {}
for с in io.open(r"C:\sender\_ops\gen-kc-test.jsonl", encoding="utf-8", errors="replace"):
    if '"итог"' not in с:
        continue
    try:
        з = json.loads(с)
    except ValueError:
        continue
    итог[str(з.get("inn"))] = з
вернуть = []
for inn, з in итог.items():
    б = " ".join(map(str, з.get("брак") or []))
    if з.get("ок") or "НЕ ПОКУПАТЕЛЬ" not in б or "переставить на meyer" in б or САМИ.search(б):
        continue
    вернуть.append((inn, з.get("имя"), б[:110]))
print("снято линзой «не покупатель» (КЦ): %d" % len(вернуть))
for inn, имя, б in вернуть:
    print("   %s %s | %s" % (inn, str(имя)[:30], б))
if ПРИМ and вернуть:
    e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with io.open(r"C:\sender\_ops\vernut-ne-pokupateley-kc.jsonl", "a", encoding="utf-8") as ж:
        for inn, _и, _б in вернуть:
            было = e.execute("SELECT verdikt_napr, verdikt_rusprom, verdikt_istochnik FROM companies WHERE inn=?", (inn,)).fetchone()
            ж.write(json.dumps({"inn": inn, "bylo": было}, ensure_ascii=False) + "\n")
            e.execute("UPDATE companies SET verdikt_napr='кц', verdikt_rusprom='покупатель', verdikt_istochnik='владелец', "
                      "verdikt_pochemu='владелец 15.10: заводы - покупатели КЦ', verdikt_ts=? WHERE inn=?", (т, inn))
        ж.flush()
        os.fsync(ж.fileno())
    e.commit()
    print("возвращено: %d" % len(вернуть))
print("=== ВЕРНУТЬ НЕ-ПОКУПАТЕЛЕЙ КЦ: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
