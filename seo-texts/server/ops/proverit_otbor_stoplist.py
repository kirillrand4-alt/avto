# -*- coding: utf-8 -*-
"""Живая проверка: просим отбор кандидатов и смотрим, нет ли среди них стопов."""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
from sender.wiring import build_deps                               # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
deps = build_deps(cfg, store, dry_run=True)
кв = None
for имя in dir(deps):
    з = getattr(deps, имя, None)
    if з is not None and hasattr(з, "candidates"):
        кв, поле = з, имя
        break
if кв is None:
    from sender.ai_quota import AiQuota
    кв, поле = AiQuota(store, db_path=cfg.get("service.db_path", БАЗА)), "создан вручную"
print("объект отбора: %s (в deps: %s)" % (type(кв).__name__, поле))
print("правка на месте: %s" % hasattr(кв, "_v_stop_liste"))

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
стоп = {str(r["value"]).strip().lower() for r in
        c.execute("SELECT value FROM suppression")}
кампании = [r["id"] for r in c.execute("SELECT id FROM campaigns ORDER BY id")]
c.close()
print("в стоп-листе значений: %d; кампании: %s" % (len(стоп), кампании))

for cid in кампании:
    try:
        люди = кв.candidates(cid, 300)
    except Exception as ex:                                        # noqa: BLE001
        print("кампания %s: отбор не сработал — %s" % (cid, ex))
        continue
    плохие = []
    for r in люди:
        почта = str(getattr(r, "email", "") or "").strip().lower()
        инн = "".join(x for x in str(getattr(r, "inn", "") or "") if x.isdigit())
        домен = почта.split("@")[-1] if "@" in почта else ""
        if почта in стоп or инн in стоп or домен in стоп:
            плохие.append(почта)
    print("кампания %-4s: отобрано %4d, из них в стоп-листе %d %s"
          % (cid, len(люди), len(плохие), плохие[:5]))
