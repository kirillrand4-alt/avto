# -*- coding: utf-8 -*-
"""Только чтение: детали привязки, письма компании, методы стора, прецедент."""
import io
import json
import sqlite3
import sys

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("=== messages: поля ===")
print("  " + ", ".join(р["name"] for р in c.execute("PRAGMA table_info(messages)")))

р = c.execute("SELECT detail_json FROM events WHERE id=350305").fetchone()
d = json.loads(р["detail_json"] or "{}")
print("\n=== detail.kind / detail.privyazka ===")
print("  kind: %s" % json.dumps(d.get("kind"), ensure_ascii=False)[:300])
print("  privyazka: %s" % json.dumps(d.get("privyazka"), ensure_ascii=False)[:600])
print("  in_reply_to_hdr: %r  references: %r"
      % (d.get("in_reply_to_hdr"), d.get("references")))
print("  inbox_mailbox: %r" % d.get("inbox_mailbox"))

print("\n=== ПИСЬМА ЭТОЙ КОМПАНИИ (recipient 33093) ===")
for m in c.execute("SELECT id, campaign_id, status, sent_at, mailbox_id,"
                   " subject FROM messages WHERE recipient_id=33093 ORDER BY id"):
    print("  msg=%s камп=%s %-9s %s ящик=%s | %s"
          % (m["id"], m["campaign_id"], m["status"], m["sent_at"],
             m["mailbox_id"], str(m["subject"])[:45]))

sys.path.insert(0, r"C:\sender")
import inspect                                                  # noqa: E402
from sender.store import Store                                  # noqa: E402
методы = [и for и, _ in inspect.getmembers(Store, inspect.isfunction)
          if "lead" in и.lower() or "event" in и.lower()]
print("\n=== МЕТОДЫ Store про лиды и события ===")
for и in методы:
    try:
        print("  %s%s" % (и, str(inspect.signature(getattr(Store, и)))[:150]))
    except (TypeError, ValueError):
        print("  %s" % и)

print("\n" + "=" * 22 + " vernut_otvety_iz_other.py " + "=" * 22)
print(io.open(r"C:\sender\server\ops\vernut_otvety_iz_other.py",
              encoding="utf-8", errors="ignore").read()[:3800])
