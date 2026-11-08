# -*- coding: utf-8 -*-
"""Владелец 06.11: «Агростандарт» — автоответ: почта сменилась на info@agrostandart73.ru. Основа — «Чулымский маслосырзавод» — Геннадий Элбакян (ego@54chmz.ru) дал контакт
chmz@molsib.com. Письмо от И. Беляева в тред его второго касания (цитата прикладывается
отправкой). Текст утверждён владельцем. [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "7326022411", "info@agrostandart73.ru", 15959
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
mb, rfc, thr, subj = st._conn.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
ТЕКСТ = """Добрый день!

Писал вам на прежний адрес agrostandart.73@mail.ru, в ответ пришло уведомление, что почта сменилась, поэтому дублирую сюда. Моё письмо ниже.

Коротко: фотосепараторы Meyer отбирают из зерна и семян примеси, которые проходят решето: того же калибра, но другого цвета или формы. Если пришлёте образец вашего зерна, бесплатно прогоним его на тестовой сортировке и покажем результат.

Подскажите, актуален ли для вас сейчас вопрос очистки зерна или подготовки семян?"""
print("с", mb, "→", КОМУ, "| тема:", subj, "| in-reply-to:", bool(rfc))
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "agrostandart-15959", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "Агростандарт: новый адрес из автоответа (владелец 08.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Агростандарт вручную)"))
