# -*- coding: utf-8 -*-
"""Деятельность компании = продукция из деклараций ФСА (владелец 22.10: «а если
давать декларации только? оквед что нам помогает»). Генерация письма берёт
описание компании из enrich.companies.activity; у компаний яруса C оно пустое,
и модель писала по ОКВЭД («Агро» с зерном стал «мясом птицы»). Пишем
«По декларациям ФСА выпускает: …» ТОЛЬКО туда, где activity пусто (сайтовую
деятельность не трогаем). Вход — дроп <файл> {ИНН: текст}. Журнал
_ops/activity-deklaracii.jsonl. Без --primenit — счёт.
    activity_iz_deklaraciy.py file=activity-c11b.json [--primenit]"""
import io
import json
import os
import sqlite3
import sys

import requests

Ф = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("file=")), "activity-c11b.json")
д = requests.get(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/" + Ф,
                 headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=120).json()
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=120)
пусто, занято, нет = [], 0, 0
for inn, т in д.items():
    r = e.execute("SELECT activity FROM companies WHERE inn=?", (inn,)).fetchone()
    if not r:
        нет += 1
    elif str(r[0] or "").strip():
        занято += 1
    else:
        пусто.append((т, inn))
print("в файле %d | впишем %d | деятельность уже есть %d | нет компании в обогащении %d" % (len(д), len(пусто), занято, нет))
if "--primenit" in sys.argv:
    with e, io.open(r"C:\sender\_ops\activity-deklaracii.jsonl", "a", encoding="utf-8") as ж:
        e.executemany("UPDATE companies SET activity=? WHERE inn=? AND COALESCE(activity,'')=''", пусто)
        for т, inn in пусто:
            ж.write(json.dumps({"inn": inn, "activity_bylo": "", "stalo": т[:80]}, ensure_ascii=False) + "\n")
    print("ПРИМЕНЕНО")
