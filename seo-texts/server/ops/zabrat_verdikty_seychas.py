# -*- coding: utf-8 -*-
"""Забрать вердикты работника с дропа немедленно, не дожидаясь круга.

ProbeSync.tick() ходит за результатом раз в interval_sec. Если работник уже
проверил, вердикты лежат на дропе, а в addr_probe их ещё нет — импортируем
руками.
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync, РЕЗУЛЬТАТ     # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = build_addr_probe(store, cfg)
цикл = build_probe_sync(store, getattr(проба, "probe_", проба), cfg)

# что лежит на дропе
свои = set()
c0 = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                     timeout=60)
for r in c0.execute("SELECT DISTINCT lower(trim(email)) e FROM confirm_reviews"
                    " WHERE campaign_id=11 AND created_at >= datetime('now','-9 hour')"
                    "   AND email LIKE '%@%'"):
    свои.add(r[0])
c0.close()
print("адресов сегодняшней партии: %d" % len(свои))

строк, наших, свежих = 0, 0, 0
порог = time.time() - 3600
try:
    сыро = цикл._дроп("GET", РЕЗУЛЬТАТ).decode("utf-8", "replace")
    for с in сыро.splitlines():
        с = с.strip()
        if not с:
            continue
        строк += 1
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        а = str(z.get("email") or "").strip().lower()
        if а in свои:
            наших += 1
        т = z.get("ts")
        if isinstance(т, (int, float)) and т >= порог:
            свежих += 1
    print("в probe-rezultat.jsonl на дропе: %d строк; из них наших %d, "
          "за последний час %d" % (строк, наших, свежих))
except Exception as e:                                        # noqa: BLE001
    print("результат с дропа не прочитан: %s" % str(e)[:140])

print("\n=== ЗАБИРАЮ ВЕРДИКТЫ ===")
т0 = time.time()
try:
    итог = цикл.забрать()
    print("   %s" % json.dumps(итог, ensure_ascii=False)[:400])
except Exception as e:                                        # noqa: BLE001
    print("   забрать() упало: %s: %s" % (type(e).__name__, str(e)[:200]))
print("   заняло %.0f с" % (time.time() - т0))

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
print("\n=== ПАРТИЯ ПОСЛЕ ИМПОРТА ===")
всего = 0
for r in c.execute(
        "SELECT COALESCE(p.verdict,'ПРОБЫ НЕТ') в, COUNT(*) n"
        "  FROM confirm_reviews cr"
        "  LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
        " WHERE cr.campaign_id=11 AND cr.created_at >= datetime('now','-9 hour')"
        " GROUP BY в ORDER BY n DESC"):
    всего += r[1]
    print("   %-16s %5d" % (r[0], r[1]))
нет = c.execute(
    "SELECT COUNT(*) FROM confirm_reviews cr"
    " LEFT JOIN addr_probe p ON p.email = lower(trim(cr.email))"
    " WHERE cr.campaign_id=11 AND cr.created_at >= datetime('now','-9 hour')"
    "   AND p.email IS NULL").fetchone()[0]
c.close()
print("\n=== ИТОГ ===")
print("писем партии: %d, из них без пробы: %d, проверено: %d"
      % (всего, нет, всего - нет))
