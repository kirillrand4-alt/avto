# -*- coding: utf-8 -*-
"""Что за входящее #218976 и от кого оно."""
import json
import sqlite3
import sys

НОМЕР = int(next((a for a in sys.argv[1:] if a.isdigit()), "218976"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
e = c.execute("SELECT * FROM events WHERE id=?", (НОМЕР,)).fetchone()
if e is None:
    print("события нет")
    raise SystemExit(0)
d = json.loads(e["detail_json"] or "{}")
print("событие #%s %s ящик %s получатель %s"
      % (e["id"], e["event_ts"], e["mailbox_id"], e["recipient_id"]))
print("")
print("ТЕКСТ ЦЕЛИКОМ:")
print(" ".join(str(d.get("snippet") or "").split())[:2500])
print("")
h = d.get("headers") or {}
if isinstance(h, dict):
    for к in ("From", "To", "Subject", "Date", "Reply-To", "Message-ID"):
        if h.get(к):
            print("   %-12s %s" % (к, str(h[к])[:150]))
print("   прочие ключи: %s" % ", ".join(sorted(d)))
for к in ("from", "kind", "privyazka", "reply_kind"):
    if d.get(к):
        print("   %-12s %s" % (к, str(d[к])[:120]))
c.close()
