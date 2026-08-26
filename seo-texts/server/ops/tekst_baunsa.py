# -*- coding: utf-8 -*-
"""Полный технический кусок яндексовых отбивок за сегодня."""
import json
import re
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
показано = 0
for r in c.execute(
        "SELECT e.detail_json, e.mailbox_id, r.email FROM events e "
        "  LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)='2026-08-26' "
        " ORDER BY e.id DESC"):
    d = json.loads(r["detail_json"] or "{}")
    т = " ".join(str(d.get("snippet") or "").split())
    if "yandex" not in т.lower():
        continue
    # Технические подробности идут после английской части
    м = re.search(r"(\d{3}\s+[45]\.\d\.\d.{0,220})", т)
    хвост = м.group(1) if м else т[-320:]
    print("--- %-34s ящик %s" % (str(r["email"])[:34], str(r["mailbox_id"])[:34]))
    print("    %s" % хвост[:300])
    for к in ("reason", "status", "smtp_code", "failed", "diagnostic"):
        if d.get(к):
            print("    %s: %s" % (к, str(d[к])[:160]))
    показано += 1
    if показано >= 8:
        break
if not показано:
    print("яндексовых отбивок за сегодня не нашлось")
c.close()
