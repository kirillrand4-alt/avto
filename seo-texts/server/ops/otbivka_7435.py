# -*- coding: utf-8 -*-
"""Где именно живёт отбивка, которую видит продажник в карточке лида."""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
ИНН = "6167128827"
from sender.config import Config                                   # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== события rid=7435 (info@impeks-don.ru) ===")
for e in c.execute("SELECT id, event_type, event_ts, mailbox_id, detail_json "
                   "  FROM events WHERE recipient_id=7435 ORDER BY event_ts"):
    d = {}
    try:
        d = json.loads(e["detail_json"] or "{}")
    except Exception:
        pass
    print("  ev=%s %s %s ящик=%s" % (e["id"], e["event_type"], e["event_ts"],
                                     e["mailbox_id"]))
    print("     ключи: %s" % sorted(d.keys())[:20])
    print("     %s" % str(d.get("snippet") or "").replace("\n", " ")[:400])
print("=== письма rid=7435 ===")
for m in c.execute("SELECT id, sent_at, status, subject FROM messages "
                   " WHERE recipient_id=7435 ORDER BY id"):
    print("  msg=%s %s %s :: %s" % (m["id"], m["sent_at"], m["status"],
                                    str(m["subject"])[:60]))
print("=== лиды по ИНН ===")
for л in c.execute("SELECT id, recipient_id, email, company_name, status "
                   "  FROM leads WHERE inn=? OR recipient_id IN (7435,29417)",
                   (ИНН,)):
    print("  лид=%s rid=%s %s %s %s" % (л["id"], л["recipient_id"], л["email"],
                                        str(л["company_name"])[:30], л["status"]))
print("=== стоп-лист / отбивки по адресу ===")
for t in ("suppressions",):
    try:
        for s in c.execute("SELECT * FROM %s WHERE email LIKE '%%impeks-don%%'" % t):
            print("  %s: %s" % (t, dict(s)))
    except Exception as e:
        print("  %s: %s" % (t, e))
c.close()

print("=== dialog_thread_company(%s) ===" % ИНН)
for it in store.dialog_thread_company(ИНН):
    print("  %s %s [%s] %s | %s :: %s"
          % (it.get("direction"), it.get("ts"), it.get("kind"),
             it.get("email"), str(it.get("subject"))[:45],
             str(it.get("body") or "").replace("\n", " ")[:110]))
