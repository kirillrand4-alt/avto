# -*- coding: utf-8 -*-
"""Полный разбор входящего с просьбой писать на другой адрес."""
import json
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row
r = c.execute("SELECT * FROM events WHERE event_type='reply'"
              " ORDER BY id DESC LIMIT 1").fetchone()
d = json.loads(r["detail_json"] or "{}") or {}
print("=== СОБЫТИЕ %s ===" % r["id"])
for к in ("event_ts", "recipient_id", "campaign_id", "message_id",
          "mailbox_id", "rfc_msgid"):
    print("   %-14s %s" % (к, r[к]))
print("   reply_kind:    %s" % d.get("reply_kind"))
print("   inbox:         %s" % d.get("inbox_mailbox"))
print("   телефон:       %s" % d.get("phone"))
заг = d.get("headers") or {}
for к in ("From", "To", "Subject", "Date", "Reply-To"):
    if заг.get(к):
        print("   %-14s %s" % (к, str(заг[к])[:110]))
print("\n   ПОЛНЫЙ snippet:\n   %s" % str(d.get("snippet") or "").replace("\n", "\n   "))

if r["recipient_id"]:
    q = c.execute("SELECT id, inn, email, company_name, contact_name, domain,"
                  "       segment, extra_json FROM recipients WHERE id=?",
                  (r["recipient_id"],)).fetchone()
    print("\n=== ПОЛУЧАТЕЛЬ ===")
    for к in ("id", "inn", "email", "company_name", "contact_name", "domain",
              "segment"):
        print("   %-14s %s" % (к, q[к]))
    доп = {}
    try:
        доп = json.loads(q["extra_json"] or "{}") or {}
    except Exception:                                         # noqa: BLE001
        pass
    print("   ключи extra: %s" % sorted(доп.keys())[:16])

print("\n=== ЧТО МЫ ЕМУ ПИСАЛИ ===")
for m in c.execute("SELECT id, campaign_id, mailbox_id, subject, body_rendered,"
                   "       substr(sent_at,1,19) когда FROM messages"
                   " WHERE recipient_id=? AND sent_at IS NOT NULL"
                   " ORDER BY id DESC LIMIT 1", (r["recipient_id"],)):
    print("   письмо %s, кампания %s, ящик %s, отправлено %s"
          % (m["id"], m["campaign_id"], m["mailbox_id"], m["когда"]))
    print("   тема: %s" % m["subject"])
    print("   --- текст ---")
    for с in str(m["body_rendered"] or "").splitlines():
        print("   | %s" % с[:110])

print("\n=== ЧТО ИЗВЕСТНО ПРО НОВЫЙ АДРЕС ===")
for а in ("nfo@kubanochka.ru", "info@kubanochka.ru"):
    p = c.execute("SELECT verdict, ts, answer, source FROM addr_probe"
                  " WHERE email=?", (а,)).fetchone()
    print("   %-24s проба: %s" % (а, ("%s (%s)" % (p["verdict"], p["source"]))
                                  if p else "не проверялся"))
c.close()
