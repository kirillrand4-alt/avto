# -*- coding: utf-8 -*-
"""Перевести лиды в «не интересно» штатным update_lead_cas с пометкой: lidy_v_ne_interesno.py "причина" ID [ID…] [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config   # noqa: E402
from sender.store import Store     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
причина = sys.argv[1]
for i in [int(a) for a in sys.argv[2:] if a.isdigit()]:
    л = store._conn.execute("SELECT id, email, company_name, status, version FROM leads WHERE id=?", (i,)).fetchone()
    print("#%s %s | %s | было: %s" % (л[0], л[1], л[2], л[3]))
    if "--katit" in sys.argv and л[3] != "not_interested":
        р = store.update_lead_cas(i, expected_version=л[4], action=причина, status="not_interested")
        print("   ->", "not_interested" if р else "НЕ ВЫШЛО (версия сменилась)")
