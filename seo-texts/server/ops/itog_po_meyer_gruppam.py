# -*- coding: utf-8 -*-
"""Что в итоге с письмами групп «мейер-рентген» и «мейер-фото».

Вопрос владельца: «заменено всё в очереди?». Считаем по самим строкам
очереди: сколько писем у этих получателей, сколько переписано (текст
отличается от того, что журнал сохранил как «было»), сколько осталось
старыми и почему.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ГРУППЫ = ("мейер-рентген", "мейер-фото")
Ж = r"C:\sender\_ops\peregeneraciya-meyer.jsonl"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

журнал = {}
for s in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    i = int(z["id"])
    # успех держим: неудачная повторная попытка не отменяет переписанное
    if журнал.get(i, {}).get("ок") and not z.get("ок"):
        continue
    журнал[i] = z

группы = store.recipient_groups().get("по_id") or {}
нужные = {rid for rid, гр in группы.items() if any(g in гр for g in ГРУППЫ)}

with store._lock:
    ряды = store._conn.execute(
        "SELECT id, recipient_id, status, COALESCE(campaign_id,0) "
        "FROM confirm_reviews").fetchall()

итог = Counter()
осталось = []
for rid, rcid, st, camp in ряды:
    if rcid is None or int(rcid) not in нужные:
        continue
    итог[f"всего писем этим получателям / {st}"] += 1
    if st != "pending":
        continue
    z = журнал.get(int(rid))
    if z and z.get("ок"):
        итог["переписано"] += 1
    elif z:
        итог[f"попытка была, но брак: {str(z.get('почему'))[:40]}"] += 1
        осталось.append((rid, z.get("фирма")))
    else:
        итог["не бралось вовсе"] += 1
        осталось.append((rid, "—"))

print(f"получателей в группах: {len(нужные)}")
for k, n in итог.most_common():
    print(f"  {n:>4}  {k}")
if осталось:
    print(f"\nостались со старым текстом ({len(осталось)}), первые 12:")
    for rid, фирма in осталось[:12]:
        print(f"  #{rid}  {str(фирма)[:44]}")
