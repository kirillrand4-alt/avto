# -*- coding: utf-8 -*-
"""Жив ли работник VPS и как убывает задание."""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync, ЗАДАНИЕ, РЕЗУЛЬТАТ  # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
цикл = build_probe_sync(store, getattr(build_addr_probe(store, cfg),
                                       "probe_", None), cfg)

for имя in ("vps-runner-zhiv.json",):
    try:
        сыро = цикл._дроп("GET", имя).decode("utf-8", "replace")
        d = json.loads(сыро)
        ts = d.get("ts") or d.get("time") or d.get("when")
        возраст = ""
        if isinstance(ts, (int, float)):
            возраст = " (%.1f мин назад)" % ((time.time() - ts) / 60.0)
        print("=== %s ===\n   %s%s" % (имя, json.dumps(d, ensure_ascii=False)[:260],
                                       возраст))
    except Exception as e:                                    # noqa: BLE001
        print("=== %s === не прочитан: %s" % (имя, str(e)[:110]))

try:
    сыро = цикл._дроп("GET", ЗАДАНИЕ).decode("utf-8", "replace")
    з = json.loads(сыро)
    if isinstance(з, dict):
        з = з.get("emails") or []
    print("\nв задании на дропе сейчас: %d адресов" % len(з))
except Exception as e:                                        # noqa: BLE001
    print("\nзадание не прочитано: %s" % str(e)[:110])

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
print("\n=== ПАРТИЯ MEYER: ВЕРДИКТЫ ===")
for r in c.execute(
        "SELECT COALESCE(p.verdict,'ПРОБЫ НЕТ') в, COALESCE(p.source,'') ист,"
        "       COUNT(*) n FROM confirm_reviews cr"
        "  LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.campaign_id=11 AND cr.created_at >= datetime('now','-8 hour')"
        " GROUP BY в, ист ORDER BY n DESC"):
    print("   %-16s источник %-10s %5d" % (r[0], r[1] or "—", r[2]))
последняя = c.execute("SELECT MAX(ts) FROM addr_probe WHERE source='проба'"
                      ).fetchone()[0]
за_час = c.execute("SELECT COUNT(*) FROM addr_probe WHERE source='проба'"
                   "  AND ts >= datetime('now','-1 hour')").fetchone()[0]
c.close()
print("\n=== ИТОГ ===")
print("последняя проба работника: %s" % последняя)
print("проб работника за последний час: %d" % за_час)
