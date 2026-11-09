# -*- coding: utf-8 -*-
"""Владелец 09.11: «МеталлПромСервис» (ГК «Баррикада») — Циркун (ac@, продажи) направил в снабжение к Елманову. Ответом в тред письма 42787; текст утверждён владельцем. [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "7814831092", "Elmanov.ilia@metpromserv.ru", 42787
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
mb, rfc, thr, subj = st._conn.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
ТЕКСТ = """Илья, добрый день!

Меня зовут Владислав, я из Компрессор Центра. Алексей Циркун из отдела продаж подсказал, что вопросы оборудования у вас ведёт снабжение.

На металлоконструкциях сжатый воздух идёт на плазменную резку, покраску и пневмоинструмент. Сейчас предприятия закладывают модернизацию на следующий год. Делаем всё под ключ: от одного компрессора до модульной станции с осушкой. Свой бренд Enger, модульные станции собираем на собственном производстве, сервис и инженеры свои. Работали с РУСАЛом, РЖД и «Алросой».

Подскажите, есть ли в планах замена или расширение компрессорной? И что сейчас стоит у вас на производстве: сколько компрессоров, какие, хватает ли воздуха?"""
print("с", mb, "→", КОМУ, "| тема:", subj, "| in-reply-to:", bool(rfc))
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "metpromserv-42787", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "МеталлПромСервис: по указанию Циркуна в снабжение (владелец 09.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: МеталлПромСервис вручную)"))
