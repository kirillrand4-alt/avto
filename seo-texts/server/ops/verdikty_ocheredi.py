# -*- coding: utf-8 -*-
"""Какие вердикты рецензента уже есть у писем, стоящих в очереди pending."""
import io
import json
import sqlite3
import sys
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
верд = {}
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = z            # последний вердикт побеждает
    except Exception:                                            # noqa: BLE001
        pass

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute("SELECT id, campaign_id, email, subject FROM confirm_reviews "
                 "WHERE status='pending' ORDER BY id").fetchall()
счёт = Counter()
for r in ряды:
    z = верд.get(r["id"])
    счёт[str((z or {}).get("verdict") or "НЕ ЧИТАНО")] += 1
print(f"pending карточек: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

# КТО НЕ ЧИТАН. Рецензент говорит «писем к рецензии: 0», а здесь их 49 —
# значит они вне его выборки: другая кампания или иной статус.
неч = [r for r in ряды if r["id"] not in верд]
print("\nне читано по кампаниям:",
      dict(Counter(int(r["campaign_id"]) for r in неч)))
print("их id:", [r["id"] for r in неч][:60])

# Сколько у «нечем проверить» и «не годно» знаков сайта — это и есть
# «наш профиль, но мало данных».
for имя in ("нечем проверить", "не годно"):
    зн = [int((верд.get(r["id"]) or {}).get("сайт_знаков") or 0)
          for r in ряды if str((верд.get(r["id"]) or {}).get("verdict") or "") == имя]
    if зн:
        пусто = sum(1 for x in зн if x < 200)
        print(f"\n  {имя}: {len(зн)} писем, из них сайт короче 200 знаков — {пусто}")
