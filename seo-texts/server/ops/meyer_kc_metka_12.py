# -*- coding: utf-8 -*-
"""12 писем Meyer, у которых компания в базе обзвона помечена только «kc».
Владелец 14.10 (вариант 2): тем, кому Meyer подходит, — «+meyer» в метку базы
обзвона; где Meyer не к месту — письмо в скип.

    meyer_kc_metka_12.py              — показать профиль компаний
    meyer_kc_metka_12.py plus=ID,ID skip=ID,ID   — применить
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

ИД = [17953, 17955, 17969, 17997, 18023, 18072, 18075, 18494, 19001, 19706, 20403, 20964]
арг = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
плюс = {int(x) for x in арг.get("plus", "").split(",") if x}
скип = {int(x) for x in арг.get("skip", "").split(",") if x}
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=30)
т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
for i in ИД:
    с = cs.get(i)
    inn = str(с.get("inn"))
    р = e.execute("SELECT name, okved, verdikt_napr, verdikt_istochnik FROM companies WHERE inn=?", (inn,)).fetchone() or ("?",) * 4
    м = o.execute("SELECT division FROM obzvon WHERE inn=?", (inn,)).fetchone()
    if not плюс and not скип:
        d = cs._cards.card(inn) if hasattr(cs._cards, "card") else {}
        пр = ""
        for k in ("site_facts", "passport", "description", "okved_name"):
            v = (d or {}).get(k)
            if v:
                пр = json.dumps(v, ensure_ascii=False)[:260]
                break
        print("#%d %s | %s | ОКВЭД %s | вердикт %s (%s) | метка %s\n    %s" % (
            i, с.get("email"), р[0], р[1], р[2], р[3], м and м[0], пр))
        continue
    if i in плюс and м and "meyer" not in (м[0] or ""):
        нов = "+".join(x for x in [(м[0] or "").strip("+"), "meyer"] if x)
        with o:
            o.execute("UPDATE obzvon SET division=? WHERE inn=?", (нов, inn))
        print("#%d %s: метка %s -> %s" % (i, р[0], м[0], нов))
    if i in скип:
        with store._lock, store._conn:
            store._conn.execute("UPDATE confirm_reviews SET status='skipped' WHERE id=? AND status='pending'", (i,))
        print("#%d %s: письмо Meyer в скип" % (i, р[0]))
print("=== MEYER/КЦ МЕТКА 12 ===")
