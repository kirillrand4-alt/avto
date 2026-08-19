# -*- coding: utf-8 -*-
"""Что панель думает о направлении письма и почему.

Письмо, чьё направление не определилось, панель показывает в ОБЕИХ
очередях. Проверяем, что возвращает letter_division и что лежит в панели.
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

ИД = [int(a) for a in sys.argv[1:] if a.isdigit()] or [2646]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

for rid in ИД:
    row = store.confirm_get(rid) or {}
    panel = row.get("panel") if isinstance(row.get("panel"), dict) else {}
    print(f"#{rid}  кампания {row.get('campaign_id')}")
    print(f"  panel.letter_division: {panel.get('letter_division')!r}")
    print(f"  panel.division:        {panel.get('division')!r}")
    print(f"  panel.company.division:"
          f" {((panel.get('company') or {}) or {}).get('division')!r}")
    print(f"  ключи панели: {sorted(panel.keys())[:14]}")
    try:
        d = cs.letter_division(row)
    except Exception as ex:                                      # noqa: BLE001
        d = f"сбой {type(ex).__name__}: {str(ex)[:80]}"
    print(f"  letter_division() -> {d!r}")
    print()

# сколько таких писем в очереди вообще
with store._lock:
    ряды = store._conn.execute(
        "SELECT id FROM confirm_reviews WHERE status IN ('pending','approved')"
    ).fetchall()
без = 0
всего = 0
for (rid,) in ряды:
    row = store.confirm_get(int(rid)) or {}
    всего += 1
    try:
        if not cs.letter_division(row):
            без += 1
    except Exception:                                            # noqa: BLE001
        без += 1
print(f"писем в очереди: {всего}, направление НЕ определилось у {без} "
      f"— они показываются в обеих очередях")
