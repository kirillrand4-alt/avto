# -*- coding: utf-8 -*-
"""Свод лёгкой проверки по ВСЕМ получателям двух партий (по группе, а не
по источнику: 1750 адресов уже жили в базе и источник у них старый)."""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ГРУППЫ = ("Россия 9000", "Белорусь 1000")
store = Store(r"C:\sender\sender.db")
по = {г: Counter() for г in ГРУППЫ}
свежие = Counter()
with store._lock:
    c = store._conn
    приговоры = {р[0] for р in c.execute(
        "SELECT lower(email) FROM addr_probe "
        "WHERE verdict IN ('нет MX','нет ящика','битый адрес')")}
    for р in c.execute(
            "SELECT lower(email) e, valid_status v, source s, extra_json x "
            "FROM recipients WHERE extra_json LIKE '%gruppy%'"):
        try:
            гр = (json.loads(р["x"] or "{}") or {}).get("gruppy") or []
        except Exception:  # noqa: BLE001
            continue
        for г in ГРУППЫ:
            if г in гр:
                по[г][str(р["v"] or "пусто")] += 1
                по[г]["всего"] += 1
                if р["e"] in приговоры:
                    по[г]["с приговором пробы"] += 1
                if р["s"] != "knigi-meyer7":
                    по[г]["жили в базе раньше"] += 1
                    свежие[str(р["v"] or "пусто")] += 1
for г in ГРУППЫ:
    print("")
    print("--- %s ---" % г)
    for к, n in по[г].most_common():
        print("   %-24s %6d" % (к, n))
print("")
print("--- у тех, кто жил в базе раньше (их статус от прошлых проверок) ---")
for к, n in свежие.most_common():
    print("   %-24s %6d" % (к, n))
print("")
print("=== СВОД ПРОВЕРКИ ПАРТИЙ ===")
for г in ГРУППЫ:
    print("   %-16s всего %5d, valid %5d, приговор %4d, непроверено %4d"
          % (г, по[г]["всего"], по[г]["valid"], по[г]["с приговором пробы"],
             по[г]["unknown"] + по[г]["пусто"]))
