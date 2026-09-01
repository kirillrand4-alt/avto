# -*- coding: utf-8 -*-
"""Только чтение: включена ли автоотправка и что за ящик №17."""
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ВСЕ НАСТРОЙКИ ПАНЕЛИ ===")
try:
    for р in s.execute("SELECT key, value FROM panel_settings ORDER BY key"):
        v = str(р["value"])
        print("  %-26s %s" % (р["key"], v[:110]))
except Exception as ex:
    кол = [r["name"] for r in s.execute("PRAGMA table_info(panel_settings)")]
    print("  колонки: %s" % кол)
    for р in s.execute("SELECT * FROM panel_settings"):
        print("  %s" % {k: str(р[k])[:80] for k in кол})

print("\n=== ЯЩИК №17 (индекс с нуля) ===")
я = list(cfg.mailboxes())
if len(я) > 17:
    mb = я[17]
    print("  mailbox_id  : %s" % mb.mailbox_id)
    print("  division    : %s" % getattr(mb, "division", "?"))
    print("  pool        : %s" % getattr(mb, "pool", "?"))
    print("  password_env: %s" % getattr(mb, "password_env", "?"))
print("  всего ящиков в конфиге: %d" % len(я))

print("\n=== ИТОГ ===")
for к in ("auto_send", "auto_send_enabled", "sending_enabled", "pause_all",
          "orchestrator_enabled"):
    try:
        print("  %-24s = %r" % (к, store.get_setting(к)))
    except Exception:
        pass
