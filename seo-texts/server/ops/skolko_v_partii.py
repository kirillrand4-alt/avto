# -*- coding: utf-8 -*-
"""Сколько получателей уже легло в партии (идёт ли запись)."""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

store = Store(r"C:\sender\sender.db")
счёт = {}
отрасли = {}
with store._lock:
    c = store._conn
    for р in c.execute(
            "SELECT extra_json, segment FROM recipients "
            "WHERE extra_json LIKE '%knigi-meyer7%'"):
        try:
            д = json.loads(р["extra_json"] or "{}") or {}
        except Exception:  # noqa: BLE001
            continue
        for г in (д.get("gruppy") or []):
            счёт[str(г)] = счёт.get(str(г), 0) + 1
        с = str(р["segment"] or "(нет)")
        отрасли[с] = отрасли.get(с, 0) + 1
    всего = c.execute(
        "SELECT COUNT(*) FROM recipients WHERE source='knigi-meyer7'").fetchone()[0]
print("строк с источником knigi-meyer7: %d" % всего)
print("")
print("=== НАШИ ДВЕ ПАРТИИ ===")
print("   строк с источником knigi-meyer7: %d" % всего)
print("   Россия 9000:    %6d" % счёт.get("Россия 9000", 0))
print("   Белорусь 1000:  %6d" % счёт.get("Белорусь 1000", 0))
print("   отраслей в segment: %d, сумма по ним %d"
      % (len(отрасли), sum(отрасли.values())))
