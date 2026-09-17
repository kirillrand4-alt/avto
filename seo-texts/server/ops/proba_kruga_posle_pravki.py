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
# письма=[] — только приём вердиктов, без чтения очереди
итог = цикл.забрать([])
прошло = time.time() - т0

стало = метка()
print("после:     последняя запись %s, строк %d" % (стало["б"], стало["n"]))
print("")
print("--- что сказал круг ---")
for к in sorted(итог):
    print("   %-28s %s" % (к, str(итог[к])[:90]))
print("")
with store._lock:
    n = store._conn.execute(
        "SELECT COUNT(*) FROM addr_probe "
        " WHERE ts >= datetime('now','-3 minutes')").fetchone()[0]
print("=" * 74)
print("=== КРУГ НА ПОЧИНЕННОМ КОДЕ ===")
print("   занял: %.1f с (было 70 с)" % прошло)
print("   строк переписано за последние 3 минуты: %d (было 29957)" % n)
