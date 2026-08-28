# -*- coding: utf-8 -*-
import json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
for eid in (183709, 182154, 59167):
    r = c.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    d = json.loads(r["detail_json"] or "{}")
    h = d.get("headers") or {}
    print("=" * 70)
    print("#%s  %s  ящик %s" % (eid, str(r["event_ts"])[:19], r["mailbox_id"]))
    print("   От:   %s" % str(h.get("From") or "")[:90])
    print("   Тема: %s" % str(h.get("Subject") or "")[:90])
    print("   In-Reply-To: %s" % str(h.get("In-Reply-To") or "—")[:70])
    print("   привязка=%s kind=%s" % (d.get("privyazka"), d.get("kind")))
    print("   --- текст ---")
    print(str(d.get("snippet") or "(пусто)")[:900])
c.close()
