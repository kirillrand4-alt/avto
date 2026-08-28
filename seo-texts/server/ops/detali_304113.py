# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT detail_json FROM events WHERE id=304113").fetchone()
d = json.loads(r["detail_json"] or "{}")
for к, v in d.items():
    if к == "headers":
        continue
    print("%-18s %r" % (к, str(v)[:300]))
h = d.get("headers") or {}
print("")
print("=== заголовки ===")
for к in ("From", "Subject", "Content-Type", "Auto-Submitted", "X-Autoreply",
          "Return-Path", "In-Reply-To", "Date", "Precedence"):
    if к in h:
        print("   %-18s %s" % (к, str(h[к])[:150]))
print("")
print("   всего заголовков: %d" % len(h))
print("   какие есть: %s" % ", ".join(sorted(h.keys()))[:300])
c.close()
