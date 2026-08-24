# -*- coding: utf-8 -*-
"""Две копии настоящих писем на ящики владельца — посмотреть, куда упадут.

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
АДРЕСА = ["kirill.martyuschov@yandex.ru", "kirillrand4@gmail.com"]

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

# --- выбор двух писем с разных доменов-отправителей ---------------------- #
строки = store._conn.execute(
    "SELECT m.id, m.subject, m.body_rendered, m.mailbox_id, m.campaign_id, "
    "       m.sequence_step_id, r.company_name, r.email "
    "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent' AND m.body_rendered IS NOT NULL "
    "   AND LENGTH(m.body_rendered) > 400 "
    " ORDER BY m.sent_at DESC LIMIT 400").fetchall()
выбор, домены = [], set()
for с in строки:
    д = str(с["mailbox_id"] or "").split("@")[-1]
    if not д or д in домены:
        continue
    домены.add(д)
    выбор.append(с)
    if len(выбор) == 2:
        break
if len(выбор) < 2:
    print("не нашёл двух писем с разных доменов — стоп")
    raise SystemExit(1)

print("\n=== ЧТО ШЛЁМ ===")
for с in выбор:
    print("\n  письмо #%s | ящик %s | исходно для %s (%s)"
          % (с["id"], с["mailbox_id"], с["email"],
             str(с["company_name"] or "")[:34]))
    print("  тема: %s" % с["subject"])
    print("  ---- тело ----")
    for строка in str(с["body_rendered"]).split("\n")[:14]:
        print("  | %s" % строка[:100])
    print("  | … всего %d знаков" % len(str(с["body_rendered"])))

print("\n=== КУДА ===")
for а in АДРЕСА:
    print("  %s" % а)

if not КАТИТЬ:
    print("\nсухой прогон. Отправка — аргумент --катить")
    raise SystemExit(0)

# --- заводим получателей и письма, шлём ---------------------------------- #
print("\n=== ОТПРАВКА ===")
ушло, сбои = 0, []
for с in выбор:
    for адрес in АДРЕСА:
        try:
            rid = store.upsert_recipient(RecipientIn(
                email=адрес, domain=адрес.split("@")[-1],
                company_name="ПРОВЕРКА ДОСТАВКИ (владелец)",
                source="проверка-доставки", tz="Europe/Moscow"))
            ключ = "proverka-%s-%s-%d" % (с["id"], адрес.split("@")[0],
                                          int(time.time()))
            mid, _ = store.enqueue_message(MessageIn(
                idempotency_key=ключ,
                campaign_id=с["campaign_id"],
                recipient_id=rid,
                sequence_step_id=с["sequence_step_id"],
                scheduled_at=datetime.now(timezone.utc)), status="scheduled")
            сообщение = store.get_message(int(mid))
            рез = живой.send(сообщение,
                             RenderedMessage(subject=str(с["subject"]),
                                             body=str(с["body_rendered"])),
                             с["mailbox_id"], manual=True, to_email=адрес)
            ушло += 1
            print("  УШЛО: %s <- ящик %s | письмо %s | rfc %s"
                  % (адрес, с["mailbox_id"], mid,
                     str(getattr(рез, "rfc_message_id", ""))[:60]))
        except Exception as e:  # noqa: BLE001
            сбои.append((адрес, с["mailbox_id"], str(e)[:160]))
            print("  СБОЙ: %s <- %s | %s: %s"
                  % (адрес, с["mailbox_id"], type(e).__name__, str(e)[:140]))

print("\nушло: %d, сбоев: %d" % (ушло, len(сбои)))
for а, я, е in сбои:
    print("  %s <- %s: %s" % (а, я, е))
