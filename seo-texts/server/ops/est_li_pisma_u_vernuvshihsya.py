# -*- coding: utf-8 -*-
"""Есть ли готовые письма у компаний, которых пересуд вернул в работу.

Если письмо уже написано и лежит снятым — восстановить его бесплатно.
Если письма не было (гейт срезал компанию ДО генерации) — придётся
генерировать, и это уже деньги.
"""
import io
import json
import sqlite3
from collections import Counter

Ж = r"C:\sender\_ops\peresud-geyta.jsonl"
вернули = set()
for s in io.open(Ж, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if str(z.get("стало")) in ("покупатель", "неясно"):
        вернули.add(str(z.get("inn")))
print(f"вернулось в работу: {len(вернули)}")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(вернули))
ряды = c.execute(
    f"SELECT cr.id rid, cr.status, COALESCE(cr.reason,'') reason, "
    f"       cr.message_id mid, r.inn, r.company_name, "
    f"       (SELECT status FROM messages WHERE id=cr.message_id) mst "
    f"FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    f"WHERE r.inn IN ({зн})", tuple(вернули)).fetchall()

с_письмом = {str(r["inn"]) for r in ряды}
print(f"из них с карточкой письма: {len(с_письмом)} | "
      f"без письма вовсе: {len(вернули - с_письмом)}")

print("\nкарточки по состоянию:")
for k, n in Counter(str(r["status"]) for r in ряды).most_common():
    print(f"  {n:>4}  {k}")

print("\nпричины снятия (топ-10):")
причины = Counter(str(r["reason"])[:70] for r in ряды
                  if str(r["status"]) == "skipped")
for k, n in причины.most_common(10):
    print(f"  {n:>4}  {k}")

# Кого можно вернуть бесплатно: письмо есть, снято, и снято именно гейтом.
можно = [r for r in ряды if str(r["status"]) == "skipped"
         and ("не наш адресат" in str(r["reason"]).lower()
              or "линза" in str(r["reason"]).lower()
              or "не покупател" in str(r["reason"]).lower())]
print(f"\nснято гейтом/линзой и письмо на месте: {len(можно)}")
for r in можно[:12]:
    print(f"  #{r['rid']} {str(r['company_name'])[:36]:<36} "
          f"письмо {r['mid']} ({r['mst']}) · {str(r['reason'])[:60]}")
