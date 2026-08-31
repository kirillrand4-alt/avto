# -*- coding: utf-8 -*-
"""Что осталось в задании на дропе и совпадает ли оно с непроверенными."""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync, ЗАДАНИЕ       # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
цикл = build_probe_sync(store, getattr(build_addr_probe(store, cfg),
                                       "probe_", None), cfg)
задание = []
try:
    з = json.loads(цикл._дроп("GET", ЗАДАНИЕ).decode("utf-8", "replace"))
    задание = з.get("emails") if isinstance(з, dict) else з
except Exception as e:                                        # noqa: BLE001
    print("задание не прочитано: %s" % str(e)[:100])
задание = [str(а).strip().lower() for а in (задание or [])]
print("в задании на дропе: %d адресов" % len(задание))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
непроверенные = set()
for r in c.execute(
        "SELECT DISTINCT lower(trim(cr.email)) e FROM confirm_reviews cr"
        " LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.campaign_id=11 AND cr.created_at >= '2026-08-31'"
        "   AND p.email IS NULL"):
    непроверенные.add(r[0])
c.close()
print("непроверенных адресов партии: %d" % len(непроверенные))
в_задании = непроверенные & set(задание)
print("из них лежат в задании: %d; ВНЕ задания: %d"
      % (len(в_задании), len(непроверенные - set(задание))))
print("\nпримеры непроверенных вне задания:")
for а in sorted(непроверенные - set(задание))[:8]:
    print("   %s" % а)
print("\nпримеры того, что лежит в задании:")
for а in задание[:6]:
    print("   %s" % а)
print("\n=== ИТОГ ===")
print("если непроверенные ВНЕ задания — их надо подложить заново")
