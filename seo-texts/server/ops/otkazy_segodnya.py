# -*- coding: utf-8 -*-
"""Спам-отказы за сегодня: по каким ящикам и сработал ли автостоп.

Я сказал владельцу «спам-отказов сегодня ноль», потому что смотрел
messages.last_error — там висели только старые, от 21.08. Журнал событий
говорит иначе: reject_spam за сегодня 2. Порог автостопа ровно такой —
два на ящик в сутки, пять на направление, — значит стоп мог уже
сработать и тихо снять ящик с отправки.

Смотрим: какие это ящики, что за ответ сервера, и что показывают гейты.
"""
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

СЕГОДНЯ = time.strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== ОТКАЗЫ ПО СПАМУ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT id, event_ts, mailbox_id, provider, message_id, detail_json "
        "FROM events WHERE event_type='reject_spam' "
        "AND substr(event_ts,1,10)=? ORDER BY id", (СЕГОДНЯ,)):
    print("  #%s %s | ящик %s | провайдер %s | письмо %s"
          % (р["id"], р["event_ts"], р["mailbox_id"], р["provider"],
             р["message_id"]))
    if р["detail_json"]:
        print("      %s" % str(р["detail_json"])[:220])

print("\n=== ОТКАЗЫ ПО ЯЩИКАМ ЗА СУТКИ ===")
for р in c.execute(
        "SELECT mailbox_id, COUNT(*) n FROM events "
        "WHERE event_type='reject_spam' AND substr(event_ts,1,10)=? "
        "GROUP BY mailbox_id ORDER BY n DESC", (СЕГОДНЯ,)):
    print("  %-44s %d" % (р["mailbox_id"], р["n"]))

print("\n=== ОТПРАВЛЕНО ПО ЯЩИКАМ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT mailbox_id, COUNT(*) n FROM events "
        "WHERE event_type='sent' AND substr(event_ts,1,10)=? "
        "GROUP BY mailbox_id ORDER BY n DESC LIMIT 20", (СЕГОДНЯ,)):
    print("  %-44s %d" % (р["mailbox_id"], р["n"]))

print("\n=== ЧТО ГОВОРЯТ ГЕЙТЫ ===")
try:
    from sender.config import Config
    from sender.store import Store
    from sender.gates import build_gates
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    гейты = build_gates(store, cfg)
    сработали = гейты.active_trips()
    if not сработали:
        print("  сработавших гейтов нет")
    for т in сработали:
        print("  " + str(т)[:220])
except Exception as e:                                         # noqa: BLE001
    print("  гейты не собрались: %s: %s" % (type(e).__name__, str(e)[:140]))

print("\n=== ПОСЛЕДНИЕ СБОИ ОТПРАВКИ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT id, status, mailbox_id, last_error, updated_at FROM messages "
        "WHERE substr(updated_at,1,10)=? AND last_error IS NOT NULL "
        "AND last_error<>'' ORDER BY id DESC LIMIT 8", (СЕГОДНЯ,)):
    print("  #%-6s %-10s %-38s %s" % (р["id"], р["status"],
                                      str(р["mailbox_id"] or "?")[:38],
                                      str(р["last_error"])[:90]))
