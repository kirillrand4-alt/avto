# -*- coding: utf-8 -*-
"""Где карточка держит текст письма, кроме поля body."""
import json, sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

СТАРЫЙ = "доведения товарных партий"
НОВЫЙ = "решето и аспирация"
store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [r[1] for r in store._conn.execute(
        "PRAGMA table_info(confirm_reviews)")]
    print("колонки confirm_reviews: %s" % ", ".join(кол))
    р = store._conn.execute(
        "SELECT * FROM confirm_reviews WHERE body LIKE ? AND status='pending' "
        " LIMIT 1", ("%" + НОВЫЙ + "%",)).fetchone()
    print("")
    print("карточка %s | %s" % (р["id"], р["email"]))
    for c in кол:
        з = р[c]
        if not isinstance(з, str) or len(з) < 40:
            continue
        есть_ст = СТАРЫЙ in з
        есть_нов = НОВЫЙ in з
        if есть_ст or есть_нов:
            print("   поле %-14s: %s%s  (%d знаков)"
                  % (c, "СТАРЫЙ " if есть_ст else "", 
                     "новый" if есть_нов else "", len(з)))
    пj = р["panel_json"] if "panel_json" in кол else None
    if пj:
        try:
            d = json.loads(пj)
        except Exception:                                      # noqa: BLE001
            d = {}

        def обойти(о, путь=""):
            if isinstance(о, dict):
                for k, v in о.items():
                    обойти(v, путь + "." + str(k))
            elif isinstance(о, list):
                for i, v in enumerate(о[:5]):
                    обойти(v, путь + "[%d]" % i)
            elif isinstance(о, str) and (СТАРЫЙ in о or НОВЫЙ in о):
                print("   panel_json%-30s: %s (%d знаков)"
                      % (путь, "СТАРЫЙ" if СТАРЫЙ in о else "новый", len(о)))
        print("")
        print("   --- где текст письма внутри panel_json ---")
        обойти(d)
