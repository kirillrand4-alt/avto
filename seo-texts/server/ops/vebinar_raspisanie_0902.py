# -*- coding: utf-8 -*-
"""Только чтение: как выглядят обычные письма в очереди и какое окно отправки."""
import datetime as dt
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
for ключ in ("send_window", "send_windows", "schedule", "send_pacing",
             "send_limits", "orchestrator"):
    зн = cfg.get(ключ, None)
    if зн is not None:
        print("  %-16s %s" % (ключ, str(dict(зн) if hasattr(зн, "keys") else зн)[:420]))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("\n=== ОБЫЧНОЕ ПИСЬМО В ОЧЕРЕДИ (pending_review) ===")
р = c.execute("SELECT * FROM messages WHERE status='pending_review'"
              " ORDER BY id DESC LIMIT 1").fetchone()
if р:
    for k in р.keys():
        if str(р[k]) not in ("None", ""):
            print("  %-18s %s" % (k, str(р[k])[:80]))

print("\n=== sequence_step_id у писем кампании 11 ===")
for x in c.execute("SELECT sequence_step_id, COUNT(*) n FROM messages"
                   " WHERE campaign_id=11 GROUP BY sequence_step_id"):
    print("  %-10s %d" % (x["sequence_step_id"], x["n"]))

print("\n=== КАК РАСПРЕДЕЛЕНЫ scheduled_at (ожидающие) ===")
for x in c.execute("SELECT substr(scheduled_at,1,13) ч, COUNT(*) n FROM messages"
                   " WHERE status IN ('scheduled','pending_review')"
                   " GROUP BY ч ORDER BY ч LIMIT 18"):
    print("  %-16s %4d" % (x["ч"], x["n"]))

print("\n=== СЕЙЧАС ===")
print("  время панели: %s" % dt.datetime.now().isoformat(timespec="seconds"))
print("  ожидающих scheduled: %d, pending_review: %d"
      % (c.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled'").fetchone()[0],
         c.execute("SELECT COUNT(*) FROM messages WHERE status='pending_review'").fetchone()[0]))
