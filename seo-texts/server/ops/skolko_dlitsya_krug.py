# -*- coding: utf-8 -*-
"""Сколько длится круг переписывания вердиктов и чем занят журнал панели."""
import io
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    c = store._conn
    р = c.execute("SELECT MIN(ts) а, MAX(ts) б, COUNT(*) n FROM addr_probe "
                  " WHERE source='проба'").fetchone()
    print("--- последний круг записи вердиктов ---")
    print("   первая строка: %s" % р["а"])
    print("   последняя:     %s" % р["б"])
    print("   строк:         %d" % р["n"])
    try:
        from datetime import datetime
        а = datetime.fromisoformat(str(р["а"]))
        б = datetime.fromisoformat(str(р["б"]))
        сек = (б - а).total_seconds()
        print("   круг занял:    %.1f с  (%.0f записей в секунду)"
              % (сек, (р["n"] / сек) if сек > 0 else 0))
        print("   интервал цикла: %s с"
              % cfg.get("probe_sync.interval_sec", 600))
    except Exception as ex:                                     # noqa: BLE001
        print("   не посчиталось: %s" % str(ex)[:80])

# журнал панели: как часто ходит цикл
for имя in ("panel.log", "sender.log", "service.log"):
    п = os.path.join(r"C:\sender\logs", имя)
    if not os.path.exists(п):
        continue
    р = os.path.getsize(п)
    with io.open(п, "rb") as f:
        f.seek(max(0, р - 400000))
        т = f.read().decode("utf-8", errors="replace")
    строки = [с for с in т.splitlines()
              if re.search(r"(?i)probe_sync|забрал|опубликов|вердикт", с)]
    if not строки:
        continue
    print("")
    print("--- %s (%.1f МБ): строки про синхронизацию проб ---" % (имя, р / 1048576.0))
    for с in строки[-12:]:
        print("   " + с[:160])
print("")
print("=" * 74)
print("=== СКОЛЬКО ДЛИТСЯ КРУГ ===")
