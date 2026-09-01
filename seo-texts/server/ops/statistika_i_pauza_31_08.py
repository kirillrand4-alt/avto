# -*- coding: utf-8 -*-
"""Почему 90 писем не видно в статистике + пауза food-sort.ru.

Без аргумента primenit ничего не меняет."""
import inspect
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ПРИМЕНИТЬ = "primenit" in sys.argv
ЯЩИКИ = ("a.erokhin@food-sort.ru", "s.kozlov@food-sort.ru")
ПРИЧИНА = ("домен food-sort.ru: нет DMARC; 6 жёстких отбивок и 3 спам-отказа "
           "на 90 писем 31.08-01.09; держать на паузе до записи DMARC")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row

print("=== ГДЕ ЭТИ 90 ПИСЕМ ЕСТЬ, А ГДЕ ИХ НЕТ ===")
mid = "a.erokhin@food-sort.ru"
n_msg = s.execute("SELECT COUNT(*) n FROM messages WHERE mailbox_id=? AND status='sent'",
                  (mid,)).fetchone()["n"]
n_ev = s.execute("SELECT COUNT(*) n FROM events WHERE mailbox_id=? AND event_type='sent'",
                 (mid,)).fetchone()["n"]
n_st = s.execute("SELECT sent_total FROM mailbox_state WHERE mailbox_id=?",
                 (mid,)).fetchone()
# send_log колонки ящика не имеет — ищем по message_id
n_sl = s.execute(
    "SELECT COUNT(*) n FROM send_log sl JOIN messages m ON m.id=sl.message_id"
    " WHERE m.mailbox_id=?", (mid,)).fetchone()["n"]
print("  messages.status='sent'      : %d   <- письма реально ушли" % n_msg)
print("  events(sent)                : %d   <- пусто" % n_ev)
print("  mailbox_state.sent_total    : %s   <- пусто" % (n_st["sent_total"] if n_st else "нет строки"))
print("  send_log (через message_id) : %d" % n_sl)

print("\n=== ЧЕМ СЧИТАЕТ analytics ===")
try:
    import sender.analytics as A
    src = inspect.getsource(A)
    for т in ("FROM events", "FROM send_log", "FROM messages", "mailbox_state"):
        print("  %-18s встречается %d раз" % (т, src.count(т)))
except Exception as ex:
    print("  ", str(ex)[:90])

print("\n=== ПАУЗА food-sort.ru ===")
v = store.get_setting("send_limits")
if isinstance(v, str) and v:
    v = json.loads(v)
if not isinstance(v, dict):
    v = {}
per = dict(v.get("per_mailbox") or {})
for m in ЯЩИКИ:
    р = s.execute("SELECT paused, pause_reason FROM mailbox_state WHERE mailbox_id=?",
                  (m,)).fetchone()
    print("  %-26s сейчас: paused=%s, потолок=%s"
          % (m, (р["paused"] if р else "нет строки"), per.get(m, "не задан")))

if ПРИМЕНИТЬ:
    for m in ЯЩИКИ:
        store.set_mailbox_paused(m, True, ПРИЧИНА)
        per[m] = 0
    v["per_mailbox"] = per
    store.set_setting("send_limits", v)
    print("\n  ПРИМЕНЕНО: обоим ящикам пауза с причиной и жёсткий потолок 0")

print("\n=== ИТОГ ===")
s2 = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s2.row_factory = sqlite3.Row
for m in ЯЩИКИ:
    р = s2.execute("SELECT paused, pause_reason FROM mailbox_state WHERE mailbox_id=?",
                   (m,)).fetchone()
    print("  %-26s paused=%s | %s"
          % (m, (р["paused"] if р else "?"), str(р["pause_reason"] if р else "")[:64]))
v2 = store.get_setting("send_limits")
if isinstance(v2, str) and v2:
    v2 = json.loads(v2)
p2 = (v2 or {}).get("per_mailbox") or {}
print("  потолки: %s" % {m: p2.get(m, "не задан") for m in ЯЩИКИ})
print("  РЕЖИМ: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "показ, без изменений"))
