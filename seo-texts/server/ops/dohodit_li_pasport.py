# -*- coding: utf-8 -*-
"""Доходит ли паспорт сайта (enrich.db/site_facts) до письма.

В обогащении 13443 паспорта с продукцией, мощностями и разбором «где нужен
воздух». Вопрос один: видел ли их генератор, когда писал письма партии.
Ищем site_facts ГДЕ УГОДНО внутри panel_json, а не только на верхнем уровне.
"""
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ENRICH = r"C:\sender\enrich.db"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряд = store._conn.execute(
        "SELECT id, inn, panel_json FROM confirm_reviews WHERE campaign_id=10"
    ).fetchall()
инн = {str(r[1]).strip() for r in ряд if r[1]}
con = sqlite3.connect(f"file:{ENRICH}?mode=ro", uri=True, timeout=10)
есть_паспорт = set()
пусто = 0
for i in инн:
    r = con.execute("SELECT facts_json FROM site_facts WHERE inn=?",
                    (i,)).fetchone()
    if r and (r[0] or "").strip():
        try:
            f = json.loads(r[0])
            if any(f.get(k) for k in ("продукция", "мощности", "сырьё",
                                      "контроль_качества")):
                есть_паспорт.add(i)
            else:
                пусто += 1
        except Exception:                                        # noqa: BLE001
            пусто += 1
con.close()
print(f"ИНН в партии: {len(инн)}")
print(f"  паспорт сайта в обогащении ЕСТЬ и не пуст: {len(есть_паспорт)}")
print(f"  строка есть, но факты пустые:              {пусто}")
print(f"  паспорта нет вовсе:                        "
      f"{len(инн) - len(есть_паспорт) - пусто}")

свод = Counter()
пример = None
for cid, i, pj in ряд:
    т = pj or ""
    if '"site_facts"' in т:
        свод["site_facts в карточке письма ЕСТЬ"] += 1
        if пример is None:
            пример = (cid, т)
    else:
        свод["site_facts в карточке НЕТ"] += 1
print()
for к, n in свод.most_common():
    print(f"  {n:>5}  {к}")
if пример:
    cid, т = пример
    p = json.loads(т)

    def найти(о, путь=""):
        if isinstance(о, dict):
            for k, v in о.items():
                if k == "site_facts":
                    print(f"  найден по пути {путь}.{k}: {str(v)[:200]}")
                найти(v, f"{путь}.{k}")
    print(f"\nпример #{cid}:")
    найти(p)
