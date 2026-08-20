# -*- coding: utf-8 -*-
"""Что сейчас лежит в задании на дропе и мои ли адреса там.

Соседняя сессия предупредила: штатный круг панели кладёт задание
ЦЕЛИКОМ (PUT), а не дописывает — наши адреса живут там до ближайшего
круга, то есть меньше десяти минут.
"""
import json
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                   # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.probe_sync import build_probe_sync, ЗАДАНИЕ           # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = build_addr_probe(store, cfg)
цикл = build_probe_sync(store, getattr(проба, "probe_", проба), cfg)

сыро = цикл._дроп("GET", ЗАДАНИЕ).decode("utf-8", "replace")
д = json.loads(сыро)
если = д.get("emails") if isinstance(д, dict) else None
список = [str(x).strip().lower() for x in (если if если is not None else д)]
print(f"адресов в задании: {len(список)}")
print("по доменам (топ-8):",
      dict(Counter(a.split('@')[-1] for a in список).most_common(8)))

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
мои = {str(r["e"]).lower() for r in c.execute(
    "SELECT lower(cr.email) e FROM messages m "
    "JOIN confirm_reviews cr ON cr.message_id=m.id "
    "LEFT JOIN addr_probe p ON p.email=lower(cr.email) "
    "WHERE cr.status IN ('approved','edited') "
    "AND m.status IN ('scheduled','sending') "
    "AND COALESCE(p.source,'') <> 'проба'")}
есть = len(мои & set(список))
print(f"\nмоих непроверенных сейчас: {len(мои)}, из них в задании: {есть}")
