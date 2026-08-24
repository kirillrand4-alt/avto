# -*- coding: utf-8 -*-
"""Что именно выбрасывает минус_класс: 756 компаний — много ли это по делу.

Владелец 24.08: «в конце проверь, что он там выкинул, многовато что-то».
Печатаем распределение по ОКВЭД и примеры названий: видно сразу, режет он
медицину с торговлей или заодно уносит живые производства.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402
from sender.target_gate import минус_класс                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
группы = store.recipient_groups().get("по_id") or {}

по_оквэд = Counter()
примеры = {}
всего = снято = 0
for rid in sorted(rid for rid, gr in группы.items() if "Партия 935" in gr):
    rec = store.get_recipient(rid)
    if not rec:
        continue
    всего += 1
    оквэд = str(getattr(rec, "okved", "") or "")
    имя = str(getattr(rec, "company_name", "") or "")
    if not минус_класс(оквэд, имя):
        continue
    снято += 1
    ключ = оквэд[:60] if оквэд.strip() else "(ОКВЭД пуст — режет по НАЗВАНИЮ)"
    по_оквэд[ключ] += 1
    примеры.setdefault(ключ, []).append(имя[:44])

print("в группе: %d, минус_класс снимает: %d (%.1f%%)"
      % (всего, снято, 100.0 * снято / всего if всего else 0))
print("\n=== ПО ЧЕМУ РЕЖЕТ ===")
for к, н in по_оквэд.most_common(25):
    print("\n  %-62s %4d" % (к, н))
    for и in примеры[к][:3]:
        print("      %s" % и)
