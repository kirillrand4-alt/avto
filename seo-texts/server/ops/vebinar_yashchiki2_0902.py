# -*- coding: utf-8 -*-
"""Только чтение: meyer-ящики с реальными id, лимитами, паузами и загрузкой."""
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
лимиты = cfg.get("send_limits.per_mailbox", {}) or {}
общий = cfg.get("send_limits.default", None)

неделя = (dt.datetime.now() - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
отпр = {}
for р in c.execute("SELECT mailbox_id, COUNT(*) n FROM messages"
                   " WHERE status='sent' AND sent_at>=? GROUP BY mailbox_id", (неделя,)):
    отпр[р["mailbox_id"]] = р["n"]
сост = {р["mailbox_id"]: dict(р) for р in c.execute("SELECT * FROM mailbox_state")}

мейер = [m for m in ящики if str(m.get("division") or m.get("segment")) == "meyer"]
print("=== MEYER-ЯЩИКИ (%d) ===" % len(мейер))
print("  %-4s %-34s %-30s %-6s %-6s %-8s %s"
      % ("id", "адрес", "имя", "лимит", "7дн", "статус", "прогрев"))
for m in мейер:
    mid = str(m.get("mailbox_id"))
    s = сост.get(mid) or {}
    адрес = m.get("login") or "?"
    пауза = bool(s.get("paused"))
    print("  %-4s %-34s %-30s %-6s %-6s %-8s %s"
          % (mid[:4], str(адрес)[:34], str(m.get("from_name"))[:30],
             str(лимиты.get(mid, общий))[:6], str(отпр.get(mid, 0))[:6],
             ("ПАУЗА:" + str(s.get("pause_reason"))[:12]) if пауза else "on",
             "ramp=%s лим=%s сег=%s всего=%s" % (s.get("ramp_day"), s.get("daily_limit"),
                                                 s.get("sent_today"), s.get("sent_total"))))

print("\n=== КЛЮЧИ ЗАПИСИ ЯЩИКА ===")
if мейер:
    print("  " + ", ".join(sorted(мейер[0].keys())))
print("\n=== КЛЮЧИ mailbox_state ===")
if сост:
    print("  " + ", ".join(sorted(list(сост.values())[0].keys())))
print("\n=== ЛИМИТЫ ===")
print("  default=%s, персональных=%d" % (общий, len(лимиты)))
print("  " + json.dumps(лимиты, ensure_ascii=False)[:600])
