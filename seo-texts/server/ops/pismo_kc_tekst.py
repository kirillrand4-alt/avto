# -*- coding: utf-8 -*-
"""Текст письма и его разметка направления: pismo_kc_tekst.py MID"""
import json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM messages WHERE id=?", (int(sys.argv[1]),)).fetchone()
for k in r.keys():
    v = r[k]
    if k in ("body_rendered", "body"):
        print(k, ":\n", (v or "")[:900]); continue
    print(k, "=", str(v)[:200])
