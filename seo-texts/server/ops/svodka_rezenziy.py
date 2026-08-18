# -*- coding: utf-8 -*-
"""Сводка рецензий: последний вердикт по каждому письму и что с ним делать."""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

последний = {}
for s in io.open(r"C:\sender\_ops\rezenzii-pisem.jsonl", encoding="utf-8",
                 errors="replace"):
    try:
        z = json.loads(s)
        последний[int(z["id"])] = str(z.get("verdict") or "?")
    except Exception:                                            # noqa: BLE001
        continue
print(f"писем в журнале: {len(последний)}")
print("последний вердикт:", dict(Counter(последний.values()).most_common()))

with store._lock:
    ряд = store._conn.execute(
        """SELECT c.id, c.status, COALESCE(r.mx_provider,'unknown')
             FROM confirm_reviews c
             LEFT JOIN recipients r ON r.id=c.recipient_id
            WHERE c.campaign_id=10""").fetchall()
СВОЙ = ("other", "unknown", "")
свод = Counter()
готовые_к_переводу = []
for cid, статус, пров in ряд:
    в = последний.get(int(cid))
    свод[(статус, в or "не смотрено")] += 1
    if статус == "pending" and в == "годно":
        if str(пров).lower() in СВОЙ:
            свод[("pending", "годно, но корпоративный сервер")] += 1
            свод[("pending", "годно")] -= 1
        else:
            готовые_к_переводу.append(cid)

print("\nстатус письма × вердикт рецензента:")
for (ст, в), n in свод.most_common():
    if n:
        print(f"  {n:>5}  {ст:<10} {в}")
print(f"\nготовы к переводу в автоотправку: {len(готовые_к_переводу)}")
print("  первые:", готовые_к_переводу[:10])
