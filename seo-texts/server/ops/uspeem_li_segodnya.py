# -*- coding: utf-8 -*-
"""Слот есть — а успеем ли: пейсинг, дневные лимиты, ёмкость окна."""
import json
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

окно = json.loads(c.execute("SELECT value FROM panel_settings "
                            " WHERE key='sending_window'").fetchone()[0])
нач = [int(x) for x in str(окно.get("start", "09:00")).split(":")[:2]]
кон = [int(x) for x in str(окно.get("end", "14:00")).split(":")[:2]]
длина = (кон[0] * 60 + кон[1] - нач[0] * 60 - нач[1]) * 60
print("окно: %s-%s (%d минут)" % (окно.get("start"), окно.get("end"), длина // 60))

for к in ("send_pacing.min_interval_sec", "send_pacing.max_interval_sec",
          "send_pacing.per_region_interval_sec", "limits.per_mailbox_daily",
          "limits.daily", "limits.per_domain_daily"):
    print("   %-38s %s" % (к, cfg.get(к, "(нет)")))

print("")
print("=== дневные лимиты ящиков ===")
лимиты = {}
for mb in cfg.mailboxes():
    л = getattr(mb, "daily_limit", None) or getattr(mb, "limit_daily", None)
    лимиты[mb.mailbox_id] = л
    if л:
        print("   %-42s %s" % (mb.mailbox_id[:42], л))
if not any(лимиты.values()):
    print("   в конфиге ящиков лимита нет — смотрим панельные настройки")
    for r in c.execute("SELECT key, value FROM panel_settings "
                       " WHERE key LIKE '%limit%' OR key LIKE '%daily%' "
                       "    OR key LIKE '%pacing%'"):
        print("   %-38s %s" % (r["key"], str(r["value"])[:80]))

сегодня = datetime.now(timezone.utc).strftime("%Y-%m-%d")
n = c.execute("SELECT COUNT(*) FROM messages WHERE substr(sent_at,1,10)=?",
              (сегодня,)).fetchone()[0]
print("")
print("уже отправлено сегодня (%s UTC): %d" % (сегодня, n))
ящиков = len(list(cfg.mailboxes()))
интервал = int(cfg.get("send_pacing.min_interval_sec", 90) or 90)
print("ящиков: %d, минимальный интервал на ящик: %d сек" % (ящиков, интервал))
print("ёмкость окна: %d писем (%d ящиков x %d слотов)"
      % (ящиков * (длина // интервал), ящиков, длина // интервал))
c.close()
