# -*- coding: utf-8 -*-
"""Кто из старых кампаний переписан с паспортом, а кто так и не вышел."""
import io
import json
import sqlite3
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\perepisat-starye.jsonl"
готово, попытки = set(), Counter()
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    i = int(z["id"])
    попытки[i] += 1
    if z.get("ок"):
        готово.add(i)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute("SELECT c.id id, r.company_name company_name FROM confirm_reviews c "
                 "LEFT JOIN recipients r ON r.id=c.recipient_id "
                 "WHERE c.status='pending' AND c.campaign_id NOT IN (10,11)"
                 ).fetchall()
не = [r for r in ряды if int(r["id"]) not in готово]
print(f"pending старых кампаний: {len(ряды)} | переписано: "
      f"{len(ряды) - len(не)} | НЕ переписано: {len(не)}")
for r in не:
    i = int(r["id"])
    print(f"  #{i} {str(r['company_name'] or '')[:44]:<44} попыток={попытки[i]}")
