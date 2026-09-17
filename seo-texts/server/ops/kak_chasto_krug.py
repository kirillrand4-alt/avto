# -*- coding: utf-8 -*-
"""Точно: когда был последний круг переписи вердиктов и как часто он ходит."""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)
print("сейчас на сервере (UTC): %s" % сейчас.isoformat(timespec="seconds"))

with store._lock:
    c = store._conn
    р = c.execute("SELECT MIN(ts) а, MAX(ts) б, COUNT(*) n FROM addr_probe "
                  " WHERE source='проба'").fetchone()
    а = datetime.fromisoformat(str(р["а"]))
    б = datetime.fromisoformat(str(р["б"]))
    print("")
    print("--- последний круг ---")
    print("   начался:  %s" % а.isoformat(timespec="seconds"))
    print("   кончился: %s" % б.isoformat(timespec="seconds"))
    print("   длился:   %.1f с, строк %d" % ((б - а).total_seconds(), р["n"]))
    print("   назад:    %.1f минут" % ((сейчас - б).total_seconds() / 60.0))

    # сравнение через datetime, а не строкой: у SQLite 'now' пробел, у нас T
    порог = (сейчас.timestamp() - 20 * 60)
    n = 0
    for (ts,) in c.execute("SELECT ts FROM addr_probe WHERE source='проба'"):
        try:
            if datetime.fromisoformat(str(ts)).timestamp() >= порог:
                n += 1
        except Exception:                                       # noqa: BLE001
            pass
    print("   строк с записью за последние 20 минут: %d" % n)

print("")
print("--- как настроен цикл ---")
for ключ in ("probe_sync.interval_sec", "probe_sync.batch",
             "addr_probe.interval_sec"):
    print("   %-28s %s" % (ключ, cfg.get(ключ, "(нет в конфиге)")))
print("")
print("=" * 74)
print("=== КАК ЧАСТО ХОДИТ КРУГ ===")
