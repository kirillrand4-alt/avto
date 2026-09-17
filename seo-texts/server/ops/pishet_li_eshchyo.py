# -*- coding: utf-8 -*-
"""Пишет ли панель в базу прямо сейчас: два замера с паузой."""
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ПАУЗА = int(sys.argv[1]) if len(sys.argv) > 1 else 150
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def замер():
    with store._lock:
        р = store._conn.execute(
            "SELECT MAX(ts) б, COUNT(*) n FROM addr_probe "
            " WHERE source='проба'").fetchone()
    return str(р["б"]), int(р["n"])


а_ts, а_n = замер()
print("замер 1: последняя запись %s, строк %d" % (а_ts[:19], а_n))
print("ждём %d с..." % ПАУЗА)
time.sleep(ПАУЗА)
б_ts, б_n = замер()
print("замер 2: последняя запись %s, строк %d" % (б_ts[:19], б_n))

двинулось = (а_ts != б_ts) or (а_n != б_n)
сейчас = datetime.now(timezone.utc)
print("")
print("время на сервере: %s" % сейчас.isoformat(timespec="seconds"))
print("")
print("=" * 74)
print("=== %s ==="
      % ("БАЗА ВСЁ ЕЩЁ ПИШЕТСЯ — проход не закончился"
         if двинулось else "ЗАПИСЬ ОСТАНОВИЛАСЬ"))
