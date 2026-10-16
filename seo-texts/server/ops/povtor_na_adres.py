# -*- coding: utf-8 -*-
"""Повтор отправленного письма на другой адрес напрямую, тем же ящиком (владелец
16.10: «вот этим можешь отправить такое же письмо» — ТВК-Р дали offer@tabris.ru,
очередь не пускает: у компании идёт переписка).

    povtor_na_adres.py <message_id> <адрес> [--katit]

Основа: копии писем владельцу.

Владелец 24.08: «на мои две почты отправь две копии любых писем любые и
протолкни вручную… посмотрим куда попадают письма».

Берём ДВА разных отправленных письма с РАЗНЫХ доменов-отправителей и шлём
каждое на оба адреса. Одним письмом провайдера от домена не отделить: если
всё уйдёт в спам, непонятно, дело в конкретном домене или в приёмнике.

Копию заводим отдельной строкой (свой получатель, своё письмо): слать
существующее сообщение повторно нельзя — send идемпотентен по status='sent'
и просто вернёт старый результат, ничего не отправив.

Сухой прогон по умолчанию, отправка — аргументом --катить.
"""
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.dtos import MessageIn, RecipientIn, RenderedMessage     # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

КАТИТЬ = "--катить" in sys.argv or "--katit" in sys.argv
АДРЕСА = [sys.argv[2].lower()]
МИД = int(sys.argv[1])

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
живой = getattr(deps.confirm, "_sender", None)
if живой is None:
    print("живой отправитель не собран — стоп")
    raise SystemExit(1)
print("отправитель dry_run=%s" % getattr(живой, "dry_run", "?"))
if getattr(живой, "dry_run", False):
    print("ОТПРАВИТЕЛЬ В СУХОМ РЕЖИМЕ — письма никуда не уйдут, стоп")
    raise SystemExit(1)


с = store._conn.execute("SELECT m.id, m.subject, m.body_rendered, m.mailbox_id, m.campaign_id, m.sequence_step_id, "
                        "m.recipient_id, m.status FROM messages m WHERE m.id=?", (МИД,)).fetchone()
print("письмо #%s (%s) ящик %s\nтема: %s\n%s" % (с["id"], с["status"], с["mailbox_id"], с["subject"], str(с["body_rendered"])[:600]))
if not КАТИТЬ:
    print("\nсухой прогон. Отправка — --katit"); raise SystemExit(0)
стар = store._conn.execute("SELECT * FROM recipients WHERE id=?", (с["recipient_id"],)).fetchone()
адрес = АДРЕСА[0]
rid = store.upsert_recipient(RecipientIn(email=адрес, domain=адрес.split("@")[-1], inn=стар["inn"],
                                         company_name=стар["company_name"], source="повтор-на-адрес", tz=стар["tz"] or "Europe/Moscow"))
mid, _ = store.enqueue_message(MessageIn(idempotency_key="povtor-%d-%s" % (МИД, адрес), campaign_id=с["campaign_id"],
                                         recipient_id=rid, sequence_step_id=с["sequence_step_id"],
                                         scheduled_at=datetime.now(timezone.utc)), status="scheduled")
рез = живой.send(store.get_message(int(mid)), RenderedMessage(subject=str(с["subject"]), body=str(с["body_rendered"]).split("\n\nС уважением,")[0]),
                 с["mailbox_id"], manual=True, to_email=адрес)
print("УШЛО:", адрес, "<-", с["mailbox_id"], "| письмо", mid, "| rfc", str(getattr(рез, "rfc_message_id", ""))[:60])
