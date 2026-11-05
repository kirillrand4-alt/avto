# -*- coding: utf-8 -*-
"""Владелец 05.11: «Чулымский маслосырзавод» — Геннадий Элбакян (ego@54chmz.ru) дал контакт
chmz@molsib.com. Письмо от И. Беляева в тред его второго касания (цитата прикладывается
отправкой). Текст утверждён владельцем. [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "5402091078", "chmz@molsib.com", 39756
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
mb, rfc, thr, subj = st._conn.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
ТЕКСТ = """Добрый день!

Меня к вам направил Геннадий из отдела продаж, сказал, что этот вопрос в вашей компетенции. Моё первое письмо ниже.

Мы поставляем рентген-детекторы Meyer: они находят в упакованном продукте стекло, металл, керамику, камень и силикон, в том числе в сливочном масле, спредах и маргарине. Перед подбором оборудования проверяем его на образцах заказчика, это бесплатно.

Подскажите, как у вас сейчас контролируют готовую продукцию на посторонние включения? И есть ли в планах оснащение или обновление линий?

Буду благодарен за ответ."""
print("с", mb, "→", КОМУ, "| тема:", subj, "| in-reply-to:", bool(rfc))
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "chulym-39756", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "Чулымский МСЗ: контакт от Геннадия (владелец 05.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Чулымский вручную)"))
