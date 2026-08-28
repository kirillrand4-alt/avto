# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
r = c.execute("SELECT event_ts, mailbox_id, detail_json FROM events "
              " WHERE id=305587").fetchone()
d = json.loads(r["detail_json"] or "{}")
h = d.get("headers") or {}
print("получено: %s | ящик %s" % (str(r["event_ts"])[:19], r["mailbox_id"]))
print("От:   %s" % str(h.get("From") or ""))
print("Тема: %s" % str(h.get("Subject") or ""))
print("=" * 70)
т = str(d.get("snippet") or "")
print(т)
print("=" * 70)
print("длина текста: %d знаков" % len(т))
c.close()
