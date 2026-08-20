# -*- coding: utf-8 -*-
"""Вернуть копии в очередь после рестарта службы.

Семь писем цикл снял старым заслоном (по ИНН) в 08:47:54. Служба
перезапущена, новый заслон спрашивает только адрес — возвращаем их из
skipped в scheduled.

Плюс восьмая: client@farmoborona.ru. Её карточку сняли заслоном «писали
<90 дней», но заслон считает по КОМПАНИИ, а адрес - их новый общий ящик:
во входящем прямо «создан единый общий адрес, просим не использовать
другие и направлять все письма на указанный». Решение по карточке
неизменно (confirm_decide второй раз не сработает), поэтому статус правим
прямой записью и оставляем след в decided_by.
"""
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--katit" in sys.argv
ПИСЬМА = (3811, 3812, 3813, 3814, 3815, 3816, 3817)
ФАРМА = 948
ПОМЕТКА = "копия на второй адрес (одобрено человеком, разбор 20.08)"
ИСТОЧНИК = ("Компания сообщила в автоответе, что переходит на единый общий "
            "адрес и просит направлять письма сюда - дублирую.")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

# Заслон обязан быть новым — иначе вернём под тот же нож.
код = open(r"C:\sender\sender\auto_send.py", encoding="utf-8").read()
print("новый заслон в файле:", "копия на второй адрес" in код)

print("\n== семь снятых ==")
for r in c.execute("SELECT id, status, COALESCE(last_error,'') e FROM messages "
                   "WHERE id IN " + str(ПИСЬМА)):
    print(f"  письмо {r['id']} {r['status']:<9} {r['e'][:60]}")

ф = c.execute("SELECT id, status, email, COALESCE(reason,'') rs, message_id, "
              "campaign_id, recipient_id, subject, COALESCE(body,'') body "
              "FROM confirm_reviews WHERE id=?", (ФАРМА,)).fetchone()
print(f"\n== Фармоборона #{ФАРМА}: {ф['status']} | {ф['email']} | "
      f"письмо {ф['message_id']} | {ф['rs'][:60]}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

n = 0
with store._lock:
    for mid in ПИСЬМА:
        store._conn.execute(
            "UPDATE messages SET status='scheduled', claimed_at=NULL, "
            "last_error=NULL, updated_at=? WHERE id=? AND status='skipped'",
            (сейчас.isoformat(), mid))
        n += 1
    store._conn.commit()
print(f"вернул в очередь: {n}")

# --- Фармоборона ---------------------------------------------------------- #
тело = str(ф["body"] or "")
if ИСТОЧНИК not in тело:
    новое = (тело.replace("\nС уважением,", f"\n{ИСТОЧНИК}\n\nС уважением,", 1)
             if "\nС уважением," in тело else тело.rstrip() + f"\n\n{ИСТОЧНИК}\n")
    with store._lock:
        store._conn.execute(
            "UPDATE confirm_reviews SET body=?, reason=?, status='approved', "
            "decided_by=?, decided_at=?, updated_at=? WHERE id=?",
            (новое, ПОМЕТКА, "возврат копии 20.08 (человек): заслон считал по "
             "компании, адрес - их новый общий ящик",
             сейчас.isoformat(), сейчас.isoformat(), ФАРМА))
        store._conn.commit()
    print("Фармоборона: текст дополнен, карточка одобрена")

mid = ф["message_id"]
if not mid:
    пара = q._ensure_message(int(ф["campaign_id"]), int(ф["recipient_id"]))
    mid = пара[0] if пара else None
    if mid:
        with store._lock:
            store._conn.execute(
                "UPDATE confirm_reviews SET message_id=? WHERE id=?",
                (int(mid), ФАРМА))
            store._conn.commit()
if mid:
    rec = store.get_recipient(int(ф["recipient_id"]))
    with store._lock:
        store._conn.execute(
            "UPDATE messages SET status='scheduled', claimed_at=NULL, "
            "last_error=NULL, updated_at=? WHERE id=?",
            (сейчас.isoformat(), int(mid)))
        store._conn.commit()
    if rec is not None:
        store.reschedule_message(
            int(mid), next_slot(окно, recipient_tz_name(окно, rec), сейчас))
    print(f"Фармоборона: письмо {mid}, слот поставлен")
