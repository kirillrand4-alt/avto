# -*- coding: utf-8 -*-
"""Почему письмо снято/в стоп-листе — прежде чем писать на этот адрес заново."""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
for cid in ids:
    with store._lock:
        r = store._conn.execute(
            "SELECT id, email, status, reason, decided_by, decided_at, inn "
            "FROM confirm_reviews WHERE id=?", (cid,)).fetchone()
    print(f"#{cid}: {tuple(r) if r else 'нет'}")
    if r:
        with store._lock:
            s = store._conn.execute(
                "SELECT scope, value, reason, source, created_at FROM "
                "suppression WHERE lower(value)=? OR value=?",
                (str(r[1]).lower(), str(r[6]))).fetchall()
        print(f"   стоп-лист: {[tuple(x) for x in s]}")
