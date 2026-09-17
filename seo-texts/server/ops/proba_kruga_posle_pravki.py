# -*- coding: utf-8 -*-
"""Один круг приёма вердиктов на починенном коде: сколько строк тронули."""
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.probe_sync import build_probe_sync                  # noqa: E402
from sender.addr_probe import build_addr_probe                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def метка():
    with store._lock:
        return store._conn.execute(
            "SELECT MAX(ts) б, COUNT(*) n FROM addr_probe "
            " WHERE source='проба'").fetchone()


было = метка()
print("до круга:  последняя запись %s, строк %d" % (было["б"], было["n"]))

цикл = build_probe_sync(store, build_addr_probe(store, cfg).probe_, cfg)
т0 = time.time()
итог = цикл.забрать()   # настоящая очередь
прошло = time.time() - т0

стало = метка()
print("после:     последняя запись %s, строк %d" % (стало["б"], стало["n"]))
print("")
print("--- что сказал круг ---")
for к in sorted(итог):
    print("   %-28s %s" % (к, str(итог[к])[:90]))
print("")
with store._lock:
    # сравнение через datetime: у SQLite 'now' пробел, у нас T
    from datetime import datetime as _dt, timezone as _tz
    порог = _dt.now(_tz.utc).timestamp() - 8 * 60
    n = 0
    for (ts,) in store._conn.execute("SELECT ts FROM addr_probe"):
        try:
            if _dt.fromisoformat(str(ts)).timestamp() >= порог:
                n += 1
        except Exception:                                       # noqa: BLE001
            pass
print("=" * 74)
print("=== КРУГ НА ПОЧИНЕННОМ КОДЕ ===")
print("   занял: %.1f с (было 70 с)" % прошло)
print("   строк переписано за последние 8 минут: %d (было 29957)" % n)
