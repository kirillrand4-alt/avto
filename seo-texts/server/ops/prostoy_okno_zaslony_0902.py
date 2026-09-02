# -*- coding: utf-8 -*-
"""Только чтение: окно отправки, заслоны и что цикл мог бы взять сейчас."""
import datetime as dt
import inspect
import io
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402
import sender.gates as G          # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

сейчас = dt.datetime.now()
print("сейчас: %s, день недели %d (пн=1)" % (сейчас.strftime("%Y-%m-%d %H:%M"),
                                             сейчас.isoweekday()))
окно = store.get_setting("sending_window", None)
print("окно из panel_settings: %s" % окно)
print("auto_send_enabled: %s" % store.get_setting("auto_send_enabled", None))

print("\n=== ЗАСЛОНЫ (gates) ===")
g = G.Gates(cfg, store)
гл = g.check_global()
print("  глобальный: tripped=%s %s" % (гл.tripped, getattr(гл, "reason", "")))
for m in cfg.get("mailboxes", [])[:6]:
    r = g.check_mailbox(m["mailbox_id"])
    if r.tripped:
        print("  ящик %s: ЗАКРЫТ %s" % (m["mailbox_id"], getattr(r, "reason", "")))
закрытых = sum(1 for m in cfg.get("mailboxes", [])
               if g.check_mailbox(m["mailbox_id"]).tripped)
print("  закрытых ящиков: %d из %d" % (закрытых, len(cfg.get("mailboxes", []))))

print("\n=== ОТКАЗЫ СПАМА ЗА 24 ЧАСА ===")
сутки = (сейчас - dt.timedelta(hours=24)).isoformat()
таб = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
if "events" in таб:
    for р in c.execute("SELECT event_type, COUNT(*) n FROM events"
                       " WHERE event_ts>=? GROUP BY event_type ORDER BY n DESC LIMIT 10",
                       (сутки,)):
        print("  %-22s %d" % (р["event_type"], р["n"]))

print("\n=== ПОСЛЕДНИЕ ОШИБКИ ПИСЕМ ===")
for р in c.execute("SELECT last_error, COUNT(*) n, MAX(updated_at) когда FROM messages"
                   " WHERE last_error IS NOT NULL AND last_error<>''"
                   " GROUP BY last_error ORDER BY когда DESC LIMIT 8"):
    print("  %s | %s | %d" % (str(р["когда"])[:19], str(р["last_error"])[:64], р["n"]))

print("\n=== ЧТО ЦИКЛ ВОЗЬМЁТ СЕЙЧАС ===")
try:
    ф = store.claim_approved_due
    print("  сигнатура: %s" % str(inspect.signature(ф))[:140])
except Exception as ex:
    print("  нет метода: %s" % str(ex)[:80])
готовы = c.execute(
    "SELECT COUNT(*) FROM messages m WHERE m.status='scheduled'"
    " AND m.scheduled_at<=? AND EXISTS (SELECT 1 FROM confirm_reviews cr"
    " WHERE cr.message_id=m.id AND cr.status IN ('approved','edited'))",
    (сейчас.isoformat(),)).fetchone()[0]
print("  одобренных и созревших: %d" % готовы)
