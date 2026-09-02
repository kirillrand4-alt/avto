# -*- coding: utf-8 -*-
"""Только чтение: какие meyer-ящики доступны, их прогрев, лимиты и загрузка."""
import datetime as dt
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

ящики = cfg.get("mailboxes", []) or []
лимиты = (cfg.get("send_limits.per_mailbox", {}) or {})
общий = cfg.get("send_limits.default", None)
print("=== ЯЩИКИ ИЗ КОНФИГА (%d) ===" % len(ящики))
сег = {}
for m in ящики:
    mid = m.get("id")
    сег[mid] = m
поле_сег = None
if ящики:
    поле_сег = [k for k in ящики[0].keys()]
print("  поля ящика: %s" % ", ".join(map(str, поле_сег or []))[:200])

сег7 = dt.datetime.now() - dt.timedelta(days=7)
отпр = {}
for р in c.execute("SELECT mailbox_id, COUNT(*) n FROM messages"
                   " WHERE status='sent' AND sent_at>=? GROUP BY mailbox_id",
                   (сег7.strftime("%Y-%m-%dT%H:%M:%S"),)):
    отпр[р["mailbox_id"]] = р["n"]

сост = {}
for р in c.execute("SELECT * FROM mailbox_state"):
    сост[р["mailbox_id"]] = dict(р)

print("\n=== СПИСОК ===")
print("  %-34s %-8s %-7s %-6s %-6s %s"
      % ("ящик", "дивизион", "статус", "лимит", "7дн", "имя отправителя"))
for m in ящики:
    mid = m.get("id")
    s = сост.get(mid) or {}
    print("  %-34s %-8s %-7s %-6s %-6s %s"
          % (str(m.get("username") or m.get("email") or mid)[:34],
             str(m.get("division") or m.get("segment") or "-")[:8],
             str(m.get("status") or ("pause" if m.get("paused") else "on"))[:7],
             str(лимиты.get(mid, общий))[:6],
             str(отпр.get(mid, 0))[:6],
             str(m.get("from_name") or "-")[:30]))

print("\n=== ИТОГ ===")
print("  всего ящиков: %d, общий лимит по умолчанию: %s" % (len(ящики), общий))
