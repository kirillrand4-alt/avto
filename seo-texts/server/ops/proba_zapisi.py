# -*- coding: utf-8 -*-
"""Свободен ли пишущий замок enrich.db: BEGIN IMMEDIATE на свежем соединении.

Три захода с разным терпением. Если BEGIN IMMEDIATE проходит быстро —
замок свободен, и молчание заливки объясняется чем-то другим.
"""
import sqlite3
import time

БАЗА = r"C:\sender\enrich.db"
итог = []
for терпение in (2, 15, 60):
    t0 = time.time()
    try:
        c = sqlite3.connect(БАЗА, timeout=терпение, isolation_level=None)
        c.execute("PRAGMA busy_timeout = %d" % (терпение * 1000))
        c.execute("BEGIN IMMEDIATE")
        прошло = time.time() - t0
        c.execute("CREATE TABLE IF NOT EXISTS _proba_zapisi (x INTEGER)")
        c.execute("INSERT INTO _proba_zapisi VALUES (1)")
        c.execute("COMMIT")
        c.execute("DROP TABLE _proba_zapisi")
        c.close()
        итог.append("терпение %2d с -> ЗАМОК ВЗЯТ за %.2f с, запись прошла"
                    % (терпение, прошло))
    except Exception as ex:                                    # noqa: BLE001
        итог.append("терпение %2d с -> НЕ ВЫШЛО за %.2f с: %s"
                    % (терпение, time.time() - t0, str(ex)[:70]))
    time.sleep(1)

# сколько строк в requisites прямо сейчас
r = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=30)
всего = r.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
наших = r.execute(
    "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro'").fetchone()[0]
r.close()

print("=" * 68)
print("=== СВОДКА: ПИШУЩИЙ ЗАМОК enrich.db ===")
print("сейчас: %s" % time.strftime("%d.%m %H:%M:%S"))
for с in итог:
    print("   " + с)
print("")
print("requisites: всего %d, с меткой checko-sbor-agro %d" % (всего, наших))
