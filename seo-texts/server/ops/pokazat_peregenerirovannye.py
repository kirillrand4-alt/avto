# -*- coding: utf-8 -*-
"""Показать письма после перегенерации рядом с текстом их сайта.

Смотреть надо три вещи разом: что говорит сайт, что говорило старое письмо
(за что рецензент его забраковал) и что говорит новое. Иначе «стало лучше»
остаётся ощущением.

    python zapusk_svoego_skripta.py ops/pokazat_peregenerirovannye.py [сколько]
"""
import io
import json
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "3"))
ЖУРНАЛ = r"C:\sender\_ops\peregeneraciya-braka.jsonl"
РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"

рец = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        рец[int(z["id"])] = z
    except Exception:                                            # noqa: BLE001
        continue

записи = []
for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        if z.get("ок"):
            записи.append(z)
    except Exception:                                            # noqa: BLE001
        continue
print(f"перегенерировано: {len(записи)}")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
con = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True, timeout=10)

for z in записи[-СКОЛЬКО:]:
    rid = int(z["id"])
    row = store.confirm_get(rid) or {}
    inn = str(row.get("inn") or "").strip()
    r = con.execute("SELECT url, text FROM site_text WHERE inn=?",
                    (inn,)).fetchone()
    сайт = (r[1] if r else "") or ""
    print("\n" + "=" * 72)
    print(f"#{rid}  {row.get('company_name') or z.get('фирма')}  "
          f"{(r[0] if r else '') or '(сайт неизвестен)'}")
    print(f"\n--- САЙТ ({len(сайт)} знаков), первые 700:")
    print(re.sub(r"\n{2,}", "\n", сайт[:700]))
    print(f"\n--- ПРЕТЕНЗИЯ РЕЦЕНЗЕНТА К СТАРОМУ:")
    print("  " + str((рец.get(rid, {}).get("pretenzii") or [""])[0])[:260])
    print(f"\n--- БЫЛО: {z.get('тема_до')}")
    print(re.sub(r"<[^>]+>", " ", str(z.get("тело_до") or ""))[:700])
    print(f"\n--- СТАЛО: {row.get('subject')}")
    print(re.sub(r"<[^>]+>", " ", str(row.get("body") or ""))[:900])
con.close()
