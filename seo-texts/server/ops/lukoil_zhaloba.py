# -*- coding: utf-8 -*-
"""Куда делось письмо «Лукойла», записанное как жалоба на спам."""
import json
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

соб = c.execute("SELECT * FROM events WHERE event_type='complaint' "
                " ORDER BY id DESC LIMIT 3").fetchall()
for e in соб:
    d = json.loads(e["detail_json"] or "{}")
    print("=== событие #%s %s ящик %s получатель %s"
          % (e["id"], str(e["event_ts"])[:19], e["mailbox_id"], e["recipient_id"]))
    print("    текст: %s" % " ".join(str(d.get("snippet") or "").split())[:600])
    print("    ключи: %s" % ", ".join(sorted(d)))
    for к in ("reply_kind", "kind", "privyazka", "from"):
        if d.get(к):
            print("    %s: %s" % (к, str(d[к])[:100]))
    rid = e["recipient_id"]
    if rid:
        r = c.execute("SELECT id, email, company_name, inn FROM recipients "
                      " WHERE id=?", (rid,)).fetchone()
        print("    получатель: #%s %s (%s) ИНН %s"
              % (r["id"], r["email"], str(r["company_name"])[:40], r["inn"]))
        with_s = c.execute("SELECT scope, value, reason, source, created_at "
                           "  FROM suppression WHERE value=?",
                           (r["email"],)).fetchall()
        print("    в стоп-листе: %s"
              % ("; ".join("%s/%s от %s" % (x["reason"], x["source"],
                                            str(x["created_at"])[:16])
                           for x in with_s) or "нет"))
        лид = c.execute("SELECT id, reply_kind, status FROM leads "
                        " WHERE recipient_id=?", (rid,)).fetchall()
        print("    карточка лида: %s"
              % ("; ".join("#%s %s/%s" % (x["id"], x["reply_kind"], x["status"])
                           for x in лид) or "НЕТ"))
        for m in c.execute("SELECT id, status, sent_at, subject FROM messages "
                           " WHERE recipient_id=? ORDER BY id DESC LIMIT 3",
                           (rid,)):
            print("    письмо #%s %s %s | %s" % (m["id"], m["status"],
                                                 str(m["sent_at"])[:16],
                                                 str(m["subject"])[:50]))
print("")
print("=== настройка авто-стоплиста по жалобам ===")
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
for к in ("imap.auto_suppress_on_complaint", "imap.auto_suppress_on_bounce"):
    print("   %-40s %s" % (к, cfg.get(к, "(нет)")))
c.close()
