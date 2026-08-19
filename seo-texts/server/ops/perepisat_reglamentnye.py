# -*- coding: utf-8 -*-
"""Переписать письма, где регламент подан причиной письма.

Заслон уже стоит в гейте, поэтому новая версия такой оборот не пропустит -
модель будет вынуждена искать мостик от задачи получателя.

Берём только pending: отправленное не переписать, снятое не нужно.
"""
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AI                               # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--катить" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

with store._lock:
    ряды = store._conn.execute(
        "SELECT id, COALESCE(edited_body, body, '') FROM confirm_reviews "
        "WHERE status='pending'").fetchall()
работа = []
for rid, тело in ряды:
    абз = [a for a in str(тело or "").strip().split("\n\n") if a.strip()]
    if any(AI._РЕГЛАМЕНТ_В_ЗАЧИНЕ.search(a) for a in абз[:3]):
        работа.append(int(rid))
print(f"к переписыванию: {len(работа)} — {работа}")
if not работа or not КАТИТЬ:
    print("сухой прогон. Катить — аргумент --катить" if работа
          else "переписывать нечего")
    raise SystemExit(0)

итоги = Counter()
t0 = time.time()
for rid in работа:
    try:
        res = q.regenerate_review(int(rid))
    except Exception as ex:                                      # noqa: BLE001
        итоги[f"сбой: {type(ex).__name__}"] += 1
        continue
    итоги["переписано" if res.get("ok")
          else f"отказ: {str(res.get('reason'))[:40]}"] += 1
    print(f"  #{rid}: {'ОК' if res.get('ok') else res.get('reason')}")
print(f"\nготово за {time.time() - t0:.0f}с")
for k, n in итоги.most_common():
    print(f"  {n:>3}  {k}")
