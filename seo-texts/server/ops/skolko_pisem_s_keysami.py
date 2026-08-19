# -*- coding: utf-8 -*-
"""Сколько уже написанных писем нарушали бы новое правило про кейсы.

Правило меняет поведение будущих партий, но полезно знать цену прошлого:
если счётчик кейсов стоит в половине писем очереди, их придётся переписать,
а если в единицах — можно не трогать.
"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import _ОПУБЛИКОВАННЫЕ_КЕЙСЫ as RX          # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

for камп, имя in ((10, "КЦ"), (11, "Meyer")):
    with store._lock:
        строки = store._conn.execute(
            "SELECT c.id, c.status, c.body FROM confirm_reviews c "
            "WHERE c.campaign_id=? AND c.body IS NOT NULL", (камп,)).fetchall()
    счёт = Counter()
    примеры = []
    for r in строки:
        тело = re.sub(r"<[^>]+>", " ", str(r["body"] or ""))
        м = RX.search(тело)
        счёт[bool(м)] += 1
        if м and str(r["status"]) in ("pending", "approved") and len(примеры) < 5:
            примеры.append((r["id"], r["status"], м.group(0)[:70]))
    всего = sum(счёт.values())
    if not всего:
        continue
    print(f"\n== {имя} (кампания {камп}): писем {всего} ==")
    print(f"  с упоминанием кейсов: {счёт[True]} "
          f"({счёт[True]/всего*100:.1f}%)")
    for i, с, ф in примеры:
        print(f"    #{i} [{с}] «{ф}»")
