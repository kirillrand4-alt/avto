# -*- coding: utf-8 -*-
"""Только чтение: почему проба адресов режет наши письма и сколько ещё срежет."""
import datetime as dt
import inspect
import re
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
у = сейчас.replace(hour=0, minute=0, second=0).isoformat()

print("время %s" % сейчас.strftime("%H:%M:%S"))
print("отправлено сегодня: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                  (у,)).fetchone()[0])
for р in c.execute("SELECT campaign_id, status, COUNT(*) k FROM messages"
                   " WHERE campaign_id IN (11,12) GROUP BY campaign_id, status"):
    print("  кампания %-3s %-14s %d" % (р["campaign_id"], р["status"], р["k"]))

print("\n=== ПОРОГ ПРОБЫ ===")
print("  addr_probe_enabled: %s" % store.get_setting("addr_probe_enabled", None))
try:
    import sender.addr_probe as AP
    исх = inspect.getsource(AP)
    for м in re.finditer(r"(не добилась ответа|адрес не существует|mark_skipped|"
                         r"catch_all|verdict)", исх):
        н = исх[:м.start()].count("\n")
        с = исх.splitlines()[н].strip()
        if с.startswith("#") or len(с) < 8:
            continue
        print("  %s" % с[:106])
except Exception as ex:
    print("  %s" % str(ex)[:120])

print("\n=== СКИПЫ ПРОБЫ ЗА СЕГОДНЯ ПО ВСЕМ КАМПАНИЯМ ===")
for р in c.execute("SELECT campaign_id, COUNT(*) k FROM messages"
                   " WHERE status='skipped' AND updated_at>=? AND last_error"
                   " LIKE '%проба адресов%' GROUP BY campaign_id", (у,)):
    print("  кампания %s: %d" % (р["campaign_id"], р["k"]))
print("  из них «не добилась ответа» (не проверила, а не мёртвый адрес): %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='skipped'"
                  " AND updated_at>=? AND last_error LIKE '%не добилась ответа%'",
                  (у,)).fetchone()[0])
print("  «адрес не существует»: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='skipped'"
                  " AND updated_at>=? AND last_error LIKE '%не существует%'",
                  (у,)).fetchone()[0])
