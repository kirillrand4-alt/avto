# -*- coding: utf-8 -*-
"""Механическая сверка: какие процессы названы в письме и есть ли они на сайте.

Не «похоже ли», а поимённо: берём из письма слова процессов и ищем их в
собранном тексте сайта и в паспорте. То, чего нет ни там, ни там, — это
достройка, ради борьбы с которой всё и затевалось.

    python zapusk_svoego_skripta.py ops/svepit_pismo_s_saytom.py <id письма> [ещё id]
"""
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ПРОЦЕССЫ = ("покрас", "окраск", "распылен", "плазменн", "лазерн", "резк",
            "гибк", "сварк", "дробеструй", "пескоструй", "пневмоинструмент",
            "прессован", "штамп", "литьё", "литье", "термообработ", "сборк",
            "фрезер", "токарн", "шлифов", "опрессовк", "продувк", "цех",
            "станк", "участок", "линия", "линии", "полный цикл", "ЛКМ")

ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
con = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=10)

for rid in ids:
    row = store.confirm_get(rid) or {}
    inn = str(row.get("inn") or "").strip()
    r = con.execute("SELECT url, text FROM site_text WHERE inn=?",
                    (inn,)).fetchone()
    сайт = ((r[1] if r else "") or "").lower()
    f = con.execute("SELECT facts_json FROM site_facts WHERE inn=?",
                    (inn,)).fetchone()
    паспорт = ((f[0] if f else "") or "").lower()
    тело = re.sub(r"<[^>]+>", " ", str(row.get("body") or "")).lower()
    print(f"\n#{rid} {row.get('company_name')}  {r[0] if r else '(нет сайта)'}"
          f"  сайт {len(сайт)} знаков")
    нашлись, нет = [], []
    for п in ПРОЦЕССЫ:
        if п.lower() in тело:
            (нашлись if (п.lower() in сайт or п.lower() in паспорт)
             else нет).append(п)
    print(f"  названо в письме и ЕСТЬ на сайте/в паспорте: {нашлись}")
    print(f"  названо в письме и НЕТ нигде:                {нет}")
con.close()
