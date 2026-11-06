# -*- coding: utf-8 -*-
"""Владелец 06.11: «Литум. Коломна» (tender@) — ответ после «азот не нужен», с перечнем КЦ из канона. Основа — «Чулымский маслосырзавод» — Геннадий Элбакян (ego@54chmz.ru) дал контакт
chmz@molsib.com. Письмо от И. Беляева в тред его второго касания (цитата прикладывается
отправкой). Текст утверждён владельцем. [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "5022094957", "tender@litum.org", 41210
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
mb, rfc, thr, subj = st._conn.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
ТЕКСТ = """Вячеслав, добрый день!

Спасибо за ответ, понял, азот и газы вам не нужны.

Но мы работаем не только с азотом. Основное направление «Компрессор Центра» — компрессорные станции под ключ, от проекта и подбора оборудования до монтажа и пусконаладки. Работаем с винтовыми компрессорами от 5 до 711 кВт и центробежными от 132 кВт до 14,5 МВт. Выпускаем модульные станции на собственном производстве и компрессоры под собственным брендом Enger, а также являемся официальным дилером 20 производителей. За плечами компании более 6 000 реализованных проектов по России.

Подскажите, актуален ли для завода в Коломне вопрос обновления или расширения компрессорного парка?"""
print("с", mb, "→", КОМУ, "| тема:", subj, "| in-reply-to:", bool(rfc))
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=(subj if subj.lower().startswith("re:") else "Re: " + subj), body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "litum-41210", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "Литум: ответ после отказа по азоту (владелец 06.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Литум вручную)"))
