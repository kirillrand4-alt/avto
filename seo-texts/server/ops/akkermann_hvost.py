# -*- coding: utf-8 -*-
"""Технический хвост отбивки akkermann: что ИМЕННО ответил их сервер."""
import json
import re
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.row_factory = sqlite3.Row
for r in c.execute("SELECT detail_json FROM events "
                   " WHERE detail_json LIKE '%akkermann%' ORDER BY id DESC LIMIT 2"):
    d = json.loads(r["detail_json"] or "{}")
    т = " ".join(str(d.get("snippet") or "").split())
    м = re.search(r"(<[^>]*akkermann[^>]*>.{0,400})", т)
    print("--- кусок про адресата ---")
    print(м.group(1)[:400] if м else т[-400:])
    for к in ("reason", "status", "smtp_code", "failed", "diagnostic"):
        if d.get(к):
            print("   %s: %s" % (к, str(d[к])[:200]))
c.close()
