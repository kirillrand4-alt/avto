# -*- coding: utf-8 -*-
"""Сколько «повторных» (extra.povtornoe) проходят заслон после правила 13.10."""
import json
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
св = Counter()
with store._lock:
    строки = [dict(р) for р in store._conn.execute(
        "SELECT id, inn, lower(email) e, extra_json FROM recipients WHERE extra_json LIKE '%povtornoe%'")]
for р in строки:
    ex = json.loads(р["extra_json"] or "{}")
    if not ex.get("povtornoe"):
        continue
    п = cs._guard(inn=р["inn"], email=р["e"])
    св["проходит" if not п else п.split(":")[0]] += 1
print("повторных: %d → %s" % (sum(св.values()), dict(св.most_common())))
print("=== ПОВТОР: СКОЛЬКО ПРОЙДУТ ===")
