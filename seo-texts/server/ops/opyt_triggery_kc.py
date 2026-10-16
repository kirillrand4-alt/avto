# -*- coding: utf-8 -*-
"""Опыт «что режет Яндекс» (владелец 16.10): письмо КЦ #22874 (Астралес) в 5
вариантах, в каждом убран один фактор; разные ящики, пауза 3 мин, на
martiushov@prokompressor.ru. Ящики снимаются с паузы на время опыта и
возвращаются в finally. Очередь КЦ должна быть пуста (kc_v_podtverzhdenie.py).

Основа: две копии настоящих писем на ящики владельца.

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


import sqlite3
ЗАХОД = "К концу года у многих деревообрабатывающих производств накапливаются задачи, которые нужно закрыть до 31 декабря: завершить запланированные закупки, заменить оборудование перед морозами, запустить новый участок. На производствах такого профиля сухой воздух и надёжная работа пневматики - основа бесперебойного процесса."
ПРЕД = "Меня зовут {имя1}, я менеджер «Компрессор Центра». Помогу подобрать винтовой компрессор от 5 до 711 кВт или модульную станцию собственного производства под вашу задачу. За плечами компании собственный бренд Enger, дилерство 20 брендов и собственное производство модульных компрессорных станций."
ПРЕД_БЕЗ_ЦИФР = "Меня зовут {имя1}, я менеджер «Компрессор Центра». Помогаю деревообрабатывающим производствам подобрать компрессор или компрессорную станцию под их задачу."
ВОПРОС = "Есть ли у «Астралеса» сейчас такая задача? Если вопросом занимается коллега, передайте ему письмо."
ПОДП = "\n\nС уважением,\nМенеджер по продажам,\n{имя}\n«Компрессор Центр»\nООО «Руспром», ИНН 2221239841"
ТЕМА = "Для главного механика: компрессорный парк"
ВАРИАНТЫ = [
  ("kirchatov.n@compressor-pro-systems.ru", "Никита Кирчатов", "1 контроль (как есть)", ТЕМА,
   "Добрый день!\n\n" + ЗАХОД + "\n\n" + ПРЕД + "\n\n" + ВОПРОС),
  ("v.melnikov@compressor-air-expert.ru", "Владислав Мельников", "2 без захода «конец года»", ТЕМА,
   "Добрый день!\n\n" + ПРЕД + "\n\n" + ВОПРОС),
  ("aleksandr.dmitriev@kompressor-air-trade.ru", "Александр Дмитриев", "3 без цифр и брендов", ТЕМА,
   "Добрый день!\n\n" + ЗАХОД + "\n\n" + ПРЕД_БЕЗ_ЦИФР + "\n\n" + ВОПРОС),
  ("dmitriev.a@kompressor-pro-expert.ru", "Александр Дмитриев", "4 обычная тема", "Компрессоры для «Астралеса»",
   "Добрый день!\n\n" + ЗАХОД + "\n\n" + ПРЕД + "\n\n" + ВОПРОС),
  ("maksim.pavlov@kompressor-pro-trade.ru", "Максим Павлов", "5 коротко, 3 предложения", "Вопрос по сжатому воздуху",
   "Добрый день!\n\nМеня зовут {имя1}, я из «Компрессор Центра», мы подбираем компрессоры для деревообработки. Подскажите, кто у вас отвечает за пневматику и сжатый воздух? Хотел бы задать ему пару вопросов."),
]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
шаг = store._conn.execute("SELECT campaign_id, sequence_step_id FROM messages WHERE id=22874").fetchone()
пауза = {в[0]: c.execute("SELECT paused, pause_reason FROM mailbox_state WHERE mailbox_id=?", (в[0],)).fetchone() for в in ВАРИАНТЫ}
def текст(тело, имя):
    return тело.format(имя1=имя.split()[0]) + ПОДП.format(имя=имя)
for я, имя, k, тема, тело in ВАРИАНТЫ:
    print("\n==== " + k + " | " + я + " | тема: " + тема + "\n" + текст(тело, имя))
if not КАТИТЬ:
    print("\nсухой прогон. Отправка — --katit")
    raise SystemExit(0)
if c.execute("SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','approved') AND campaign_id IN (1,5,6,10,15,16)").fetchone()[0]:
    print("очередь КЦ не пуста — стоп")
    raise SystemExit(1)
try:
    with c:
        for я in пауза:
            c.execute("UPDATE mailbox_state SET paused=0 WHERE mailbox_id=?", (я,))
    for н, (я, имя, k, тема, тело) in enumerate(ВАРИАНТЫ):
        try:
            адрес = АДРЕСА[0]
            rid = store.upsert_recipient(RecipientIn(email=адрес, domain=адрес.split("@")[-1],
                  company_name="ПРОВЕРКА ДОСТАВКИ (владелец)", source="проверка-доставки", tz="Europe/Moscow"))
            mid, _ = store.enqueue_message(MessageIn(idempotency_key="opyt-%d-%d" % (н, int(time.time())),
                  campaign_id=шаг[0], recipient_id=rid, sequence_step_id=шаг[1],
                  scheduled_at=datetime.now(timezone.utc)), status="scheduled")
            живой.send(store.get_message(int(mid)), RenderedMessage(subject=тема, body=текст(тело, имя)),
                       я, manual=True, to_email=адрес)
            print("УШЛО:", k, "<-", я)
        except Exception as e:  # noqa: BLE001
            print("СБОЙ:", k, "<-", я, type(e).__name__, str(e)[:120])
        if н < len(ВАРИАНТЫ) - 1:
            time.sleep(180)
finally:
    with c:
        for я, row in пауза.items():
            if row:
                c.execute("UPDATE mailbox_state SET paused=?, pause_reason=? WHERE mailbox_id=?", (row[0], row[1], я))
    print("пауза ящиков возвращена")
