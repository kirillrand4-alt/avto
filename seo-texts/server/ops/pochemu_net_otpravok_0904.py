# -*- coding: utf-8 -*-
"""Только чтение: почему нет отправок. Время в базе UTC, сверяем аккуратно."""
import datetime as dt
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
мск = dt.datetime.now()
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
print("сейчас: %s МСК / %s UTC, день недели %d"
      % (мск.strftime("%Y-%m-%d %H:%M"), utc.strftime("%H:%M"), мск.isoweekday()))
print("окно: %s" % store.get_setting("sending_window", None))
print("автоотправка: %s" % store.get_setting("auto_send_enabled", None))

print("\n=== ОТПРАВЛЕНО ===")
for д in (0, 1, 2):
    сут = (utc - dt.timedelta(days=д)).replace(hour=0, minute=0, second=0).isoformat()
    кон = (utc - dt.timedelta(days=д - 1)).replace(hour=0, minute=0,
                                                   second=0).isoformat()
    n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent'"
                  " AND sent_at>=? AND sent_at<?", (сут, кон)).fetchone()[0]
    print("  %s: %d" % (сут[:10], n))
п = c.execute("SELECT sent_at, campaign_id, mailbox_id FROM messages"
              " WHERE status='sent' ORDER BY sent_at DESC LIMIT 3").fetchall()
for р in п:
    print("  последнее: %s UTC | кампания %s | %s"
          % (str(р["sent_at"])[:19], р["campaign_id"], р["mailbox_id"]))

print("\n=== ПАРТИЯ 13 ===")
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
for р in c.execute("SELECT scheduled_at, COUNT(*) k FROM messages WHERE campaign_id=13"
                   " GROUP BY scheduled_at ORDER BY scheduled_at LIMIT 4"):
    print("  срок %s: %d" % (str(р["scheduled_at"])[:19], р["k"]))

print("\n=== СОЗРЕЛО И ОДОБРЕНО ПО ВСЕЙ БАЗЕ ===")
n = c.execute("SELECT COUNT(*) FROM messages m WHERE m.status='scheduled'"
              " AND m.scheduled_at<=? AND (SELECT cr.status FROM confirm_reviews cr"
              " WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1)"
              " IN ('approved','edited')", (мск.isoformat(),)).fetchone()[0]
print("  готовых к отправке прямо сейчас: %d" % n)
print("  висят в sending: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sending'").fetchone()[0])

print("\n=== СЛУЖБА ===")
import subprocess
out = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\""
     " | Where-Object { $_.CommandLine -match 'serve-api' }"
     " | ForEach-Object { \"pid=$($_.ProcessId) запущен $($_.CreationDate)\" };"
     " (Get-Service SenderPanel).Status"],
    capture_output=True, text=True, timeout=60)
print("  " + (out.stdout or "").strip().replace("\n", "\n  ")[:300])
