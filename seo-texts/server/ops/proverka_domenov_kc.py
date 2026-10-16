# -*- coding: utf-8 -*-
"""Проверка домена (владелец 16.10: «отправь разные письма с этих 5 доменов, которые
точно не похожи на спам»): с одного ящика каждого домена КЦ — своё короткое
непродающее письмо на martiushov@prokompressor.ru, пауза 3 мин. Если и оно в
спаме — дело в домене, не в тексте.

Основа — копии КЦ владельцу (16.10: «отправь мне на ящик по одному письму с компрессорных
ящиков копий как ты отправляешь, посмотрю в какую папку кладётся»): с каждого
ящика пула КЦ его последнее отправленное письмо на martiushov@prokompressor.ru.

Исходно (24.08): две копии настоящих писем на ящики владельца.

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
АДРЕСА = ["martiushov@prokompressor.ru"]

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
    " ORDER BY m.sent_at DESC LIMIT 5000").fetchall()
КЦ = ("compressor-", "kompressor-")
выбор, ящики = [], set()
for с in строки:
    я = str(с["mailbox_id"] or "")
    д = я.split("@")[-1]
    # по одному письму на ДОМЕН и с паузой (владелец 16.10: «не 28… чтобы не
    # пришло 28 писем за минуту, ясное дело уйдут в спам»)
    if not я or д in ящики or not any(к in д for к in КЦ):
        continue
    ящики.add(д)
    выбор.append(с)
print("доменов КЦ: %d" % len(выбор))
СВОИ = [
    ("Встреча в четверг", "Кирилл, добрый день!\n\nПодскажите, получится в четверг созвониться минут на двадцать? Хотел обсудить, как удобнее согласовывать заявки с вашей стороны, чтобы не терять письма между отделами.\n\nЕсли четверг неудобен, напишите, какой день подходит."),
    ("Документы по прошлой поставке", "Добрый день, Кирилл!\n\nНашёл в почте вашу просьбу про закрывающие документы по прошлой поставке. Проверю с бухгалтерией сегодня и пришлю скан до конца недели.\n\nЕсли нужны оригиналы, подскажите адрес, отправлю почтой."),
    ("Уточнение по адресу доставки", "Кирилл, здравствуйте.\n\nУточните, пожалуйста, на какой адрес лучше направлять корреспонденцию: на юридический или на склад? В прошлый раз курьер ездил дважды.\n\nСпасибо!"),
    ("Контакт инженера", "Добрый день!\n\nКирилл, вы спрашивали контакт нашего сервисного инженера. Его зовут Алексей, он на связи по будням с девяти до шести, удобнее писать на почту, он отвечает в течение дня.\n\nЕсли будет удобнее, могу организовать звонок втроём."),
    ("Спасибо за встречу", "Кирилл, спасибо за вчерашнюю встречу, было полезно.\n\nЗапишу договорённости и пришлю вам на согласование, чтобы ничего не потерялось. Если что-то упустил, поправьте, пожалуйста."),
]
for i, с in enumerate(выбор):
    с = dict(с); с["subject"], с["body_rendered"] = СВОИ[i % len(СВОИ)]; выбор[i] = с
print("\n=== ЧТО ШЛЁМ ===")
for с in выбор:
    print("\n  письмо #%s | ящик %s | исходно для %s (%s)"
          % (с["id"], с["mailbox_id"], с["email"],
             str(с["company_name"] or "")[:34]))
    print("  тема: %s" % с["subject"])
    print("  ---- тело ----")
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
            if с is not выбор[-1]:
                time.sleep(180)
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
