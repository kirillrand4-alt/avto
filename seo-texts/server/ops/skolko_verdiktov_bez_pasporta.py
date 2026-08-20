# -*- coding: utf-8 -*-
"""Сколько компаний уже осуждено гейтом БЕЗ паспорта — и потому под вопросом.

Кэш гейта вечен: judge() возвращает вердикт по ИНН и повторно не судит.
Значит все, кого срезали до сегодняшней правки, срезаны навсегда — включая
тех, кого замер показал покупателями.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("вердикты гейта:")
for r in c.execute("SELECT verdict, COUNT(*) n FROM target_verdicts "
                   "GROUP BY verdict ORDER BY n DESC"):
    print(f"  {r['n']:>6}  {r['verdict']}")

print("\n«не покупатель» по дням вынесения:")
for r in c.execute("SELECT substr(ts,1,10) d, COUNT(*) n FROM target_verdicts "
                   "WHERE verdict='не покупатель' GROUP BY d ORDER BY d DESC "
                   "LIMIT 10"):
    print(f"  {r['d']}  {r['n']}")

# У скольких из них вообще есть паспорт — то есть кого имеет смысл пересудить.
import sys                                                       # noqa: E402
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
счёт = Counter()
for r in c.execute("SELECT inn FROM target_verdicts WHERE verdict='не покупатель'"):
    счёт["с паспортом" if q._pasport_dlya_geyta(str(r["inn"]))
         else "без паспорта"] += 1
print("\nсреди «не покупатель»:", dict(счёт))
