# -*- coding: utf-8 -*-
"""Только чтение: событие 350305 целиком и как раньше возвращали из other."""
import io
import json
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
р = c.execute("SELECT * FROM events WHERE id=350305").fetchone()
d = json.loads(р["detail_json"] or "{}")
h = d.get("headers") or {}
print("=== СОБЫТИЕ 350305 ===")
print("тип=%s ts=%s ящик=%s rfc=%s"
      % (р["event_type"], р["event_ts"], р["mailbox_id"], р["rfc_msgid"]))
for к in ("From", "To", "Subject", "Date", "In-Reply-To", "References",
          "Message-ID", "Return-Path"):
    if к in h:
        print("  %-13s %s" % (к, str(h[к])[:160]))
print("  ключи detail: %s" % list(d.keys()))
for к in ("text", "body", "snippet", "plain", "preview"):
    if d.get(к):
        print("  %s: %s" % (к, str(d[к])[:400].replace("\n", " | ")))

print("\n=== ЧТО ПИСАЛИ НА ЭТОТ ЯЩИК ЭТОЙ КОМПАНИИ ===")
for m in c.execute(
        "SELECT id, campaign_id, status, sent_at, mailbox_id, subject,"
        " rfc_msgid FROM messages WHERE recipient_id=33093 ORDER BY id"):
    print("  msg=%s камп=%s %s %s ящик=%s rfc=%s | %s"
          % (m["id"], m["campaign_id"], m["status"], m["sent_at"],
             m["mailbox_id"], str(m["rfc_msgid"])[:40], str(m["subject"])[:40]))

print("\n" + "=" * 24 + " vernut_otvety_iz_other.py " + "=" * 24)
print(io.open(r"C:\sender\server\ops\vernut_otvety_iz_other.py",
              encoding="utf-8", errors="ignore").read()[:4200])
