# -*- coding: utf-8 -*-
"""Сколько писем в очереди болеют тем же, чем #1240.

Два брака: приветствие с фамилией и заход с чужого регламента. Оба теперь
ловит гейт, но в очереди уже лежат письма, написанные до правки. Считаем их
поимённо - и по кампаниям, чтобы понимать масштаб.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AI                               # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    ряды = store._conn.execute(
        "SELECT id, COALESCE(campaign_id,0), status, COALESCE(body,'') "
        "FROM confirm_reviews WHERE status IN ('pending','approved')"
    ).fetchall()

счёт = Counter()
имена = []
регламент = []
for rid, camp, st, тело in ряды:
    ф = AI._familiya_v_privetstvii(тело)
    куски = str(тело or "").strip().split("\n\n")
    зачин = " ".join(куски[:2])[:400]
    р = bool(AI._РЕГЛАМЕНТ_В_ЗАЧИНЕ.search(зачин))
    if ф:
        счёт[f"фамилия в приветствии / кампания {camp} / {st}"] += 1
        имена.append((rid, ф))
    if р:
        счёт[f"заход с регламента / кампания {camp} / {st}"] += 1
        регламент.append((rid, зачин[:70]))

print(f"проверено писем: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
print(f"\nфамилия в приветствии — {len(имена)}, первые 10:")
for rid, ф in имена[:10]:
    print(f"  #{rid}  «{ф}»")
print(f"\nзаход с регламента — {len(регламент)}, первые 10:")
for rid, з in регламент[:10]:
    print(f"  #{rid}  {з}")
