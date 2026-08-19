# -*- coding: utf-8 -*-
"""Что на сайте асфальтобетонщика: есть ли там компрессорные факты.

Владелец: «асфальтобетон разбери сайт, нет ли там компрессорных фактов».
Классификатор отнёс «СК Дорожник-2» к КЦ, а письмо ему ушло мейеровское.
Проверяем по первоисточнику — паспорту и сырому тексту сайта.
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
ИМЯ = " ".join(a for a in sys.argv[1:] if not a.startswith("-")) or "ДОРОЖНИК"
ENRICH = r"C:\sender\enrich.db"

from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    # ПО ИНН, ЕСЛИ ОН ДАН. Поиск по имени взял профсоюзную организацию
    # локомотивного депо вместо дорожной компании — «Дорожник» в названии
    # есть у обеих.
    if ИМЯ.strip().isdigit():
        ряды = store._conn.execute(
            "SELECT id, inn, company_name, domain, okved, email "
            "FROM recipients WHERE inn=? LIMIT 5", (ИМЯ.strip(),)).fetchall()
    else:
        ряды = store._conn.execute(
            "SELECT id, inn, company_name, domain, okved, email FROM recipients "
            "WHERE company_name LIKE ? LIMIT 5", (f"%{ИМЯ}%",)).fetchall()
if not ряды:
    print(f"компаний по «{ИМЯ}» не нашёл"); raise SystemExit(1)
for r in ряды:
    print(f"  {r['inn']} · {r['company_name']} · {r['domain']} · "
          f"ОКВЭД {r['okved']}")
цель = ряды[0]
инн = str(цель["inn"])
print(f"\n=== разбираю {цель['company_name']} (ИНН {инн}) ===")

con = sqlite3.connect(f"file:{ENRICH}?mode=ro", uri=True, timeout=10)
row = con.execute("SELECT facts_json FROM site_facts WHERE inn=?",
                  (инн,)).fetchone()
print("\n--- ПАСПОРТ САЙТА ---")
if row and (row[0] or "").strip():
    d = json.loads(row[0])
    for k, v in d.items():
        if v in (None, "", [], {}):
            continue
        print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:400]}")
else:
    print("  паспорта нет")

текст = ""
try:
    t = con.execute("SELECT * FROM site_text WHERE inn=?", (инн,)).fetchone()
    if t:
        имена = [c[0] for c in con.execute(
            "SELECT * FROM site_text LIMIT 1").description]
        d2 = dict(zip(имена, t))
        текст = " ".join(str(v) for v in d2.values() if isinstance(v, str))
except Exception as ex:                                          # noqa: BLE001
    print("site_text:", str(ex)[:80])
con.close()

СЛОВА = ("компрессор", "сжатый воздух", "пневмо", "пневматик", "отбойн",
         "перфоратор", "продувк", "покрас", "окрас", "дробеструй",
         "пескоструй", "азот", "кислород", "опрессовк", "асфальтобетон",
         "битум", "дробильн", "грохот", "смесител", "мастерск", "ремонт",
         "гараж", "спецтехник", "парк техник")
print(f"\n--- СЛОВА В ТЕКСТЕ САЙТА ({len(текст)} знаков) ---")
if not текст:
    print("  сырого текста сайта в базе нет")
else:
    нашли = []
    for w in СЛОВА:
        for m in re.finditer(re.escape(w), текст, re.I):
            a = max(0, m.start() - 70)
            нашли.append((w, re.sub(r"\s+", " ", текст[a:m.end() + 70])))
            break
    if not нашли:
        print("  ни одного из компрессорных слов не встретилось")
    for w, ctx in нашли:
        print(f"  [{w}] …{ctx}…")
