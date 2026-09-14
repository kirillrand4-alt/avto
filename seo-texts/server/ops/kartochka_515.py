# -*- coding: utf-8 -*-
"""Карточка вернувшегося лида целиком — как её увидит продавец."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ЛИД = int(sys.argv[1]) if len(sys.argv) > 1 else 515
store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    кол = [x[1] for x in c.execute("PRAGMA table_info(leads)")]
    р = c.execute("SELECT * FROM leads WHERE id=?", (ЛИД,)).fetchone()
    if not р:
        raise SystemExit("лида %s нет" % ЛИД)
    for k in кол:
        з = р[k]
        if з in (None, ""):
            continue
        s = str(з)
        if len(s) > 100:
            print("   --- %s ---" % k)
            print(s[:1400])
        else:
            print("   %-18s %s" % (k, s))
print("")
print("=" * 74)
print("=== КАРТОЧКА ЛИДА %d ===" % ЛИД)
