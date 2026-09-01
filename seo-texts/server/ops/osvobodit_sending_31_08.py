# -*- coding: utf-8 -*-
"""Снять зависшую аренду с писем в статусе sending.

Трогаем ТОЛЬКО те, у кого нет ни одного признака реальной отправки:
ни sent_at, ни rfc_message_id, ни события sent, ни записи send_log.
Без аргумента primenit ничего не меняет."""
import inspect
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

ПРИМЕНИТЬ = "primenit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("=== методы Store про статус письма ===")
for имя in sorted(dir(store)):
    if any(k in имя for k in ("reschedule", "release", "message_status", "set_message")):
        try:
            print("  %-26s %s" % (имя, str(inspect.signature(getattr(store, имя)))[:90]))
        except Exception:
            pass

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
цель = []
for р in s.execute("SELECT id FROM messages WHERE status='sending'"):
    mid = р["id"]
    d = s.execute("SELECT sent_at, rfc_message_id FROM messages WHERE id=?",
                  (mid,)).fetchone()
    ev = s.execute("SELECT COUNT(*) n FROM events WHERE message_id=? AND event_type='sent'",
                   (mid,)).fetchone()["n"]
    sl = s.execute("SELECT COUNT(*) n FROM send_log WHERE message_id=?",
                   (mid,)).fetchone()["n"]
    if not d["sent_at"] and not d["rfc_message_id"] and ev == 0 and sl == 0:
        цель.append(mid)
    else:
        print("  #%s ПРОПУСКАЮ: есть признак отправки" % mid)

print("\n=== к освобождению: %d писем ===" % len(цель))
print("  %s" % цель)

if ПРИМЕНИТЬ and цель:
    # Штатной функцией панели, а не сырым UPDATE: release_message знает, в
    # какой статус вернуть письмо и что ещё при этом почистить.
    ок = 0
    for mid in цель:
        try:
            if store.release_message(mid):
                ок += 1
            else:
                print("  #%s release_message вернул False" % mid)
        except Exception as ex:
            print("  #%s ОШИБКА: %s" % (mid, str(ex)[:70]))
    print("  ОСВОБОЖДЕНО: %d из %d" % (ок, len(цель)))

print("\n=== ИТОГ ===")
s2 = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s2.row_factory = sqlite3.Row
for р in s2.execute("SELECT status, COUNT(*) n FROM messages"
                    " WHERE status IN ('sending','scheduled') GROUP BY status"):
    print("  %-12s %d" % (р["status"], р["n"]))
print("  РЕЖИМ: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "показ без изменений"))
