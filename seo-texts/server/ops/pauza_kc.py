# -*- coding: utf-8 -*-
"""Пауза/снятие паузы ящиков КЦ: pauza_kc.py on|off [причина]. Яндекс режет первые
письма новых доменов КЦ «подозрение на спам» — держим ящики, пока не разберёмся."""
import sqlite3
import sys
import time
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
кц = [mb.mailbox_id for mb in cfg.mailboxes() if mb.division == "kc"]
вкл = sys.argv[1] == "on"
прич = " ".join(sys.argv[2:]) or "владелец/разбор: спам-отказы Яндекса на новых доменах КЦ"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
with c:
    n = c.execute("UPDATE mailbox_state SET paused=?, pause_reason=?, updated_at=? WHERE mailbox_id IN (%s)" % ",".join("?" * len(кц)),
                  [1 if вкл else 0, прич if вкл else None, time.strftime("%Y-%m-%dT%H:%M:%S")] + кц).rowcount
print("ящиков КЦ %s: %d" % ("на паузе" if вкл else "снято с паузы", n))
print("отправлено КЦ сегодня:", c.execute("SELECT count(*) FROM events WHERE event_type='sent' AND event_ts>=date('now') AND mailbox_id IN (%s)" % ",".join("?" * len(кц)), кц).fetchone()[0],
      "спам-отказов:", c.execute("SELECT count(*) FROM events WHERE event_type='reject_spam' AND event_ts>=date('now') AND mailbox_id IN (%s)" % ",".join("?" * len(кц)), кц).fetchone()[0])
print("=== ПАУЗА КЦ ===")
