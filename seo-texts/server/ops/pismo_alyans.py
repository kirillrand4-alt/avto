# -*- coding: utf-8 -*-
"""Владелец 06.11: «ПК Альянс» — Марина (продажи) просила писать на общую pk-alyanss@mail.ru. Основа — «Чулымский маслосырзавод» — Геннадий Элбакян (ego@54chmz.ru) дал контакт
chmz@molsib.com. Письмо от И. Беляева в тред его второго касания (цитата прикладывается
отправкой). Текст утверждён владельцем. [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "7751274752", "pk-alyanss@mail.ru", 42450
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
mb, rfc, thr, subj = st._conn.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
ТЕКСТ = """Добрый день!

Марина из отдела продаж посоветовала отправить предложение на эту почту, чтобы его посмотрели директор или управляющий. Моё первое письмо ниже.

Коротко: мы ведём проекты по сжатому воздуху на производствах, от отдельного компрессора до модульной станции с осушкой и генерацией азота. На литейном производстве сжатый воздух нужен формовочным линиям, пневмоинструменту и обдуву готовых изделий. Среди наших заказчиков РЖД, «Алроса» и «Северсталь», сервис и инженеры свои.

Подскажите, есть ли в планах на ближайшие месяцы модернизация или расширение компрессорной? Если удобнее, подготовим расчёт под ваше производство."""
print("с", mb, "→", КОМУ, "| тема:", subj, "| in-reply-to:", bool(rfc))
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "alyans-42450", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "ПК Альянс: по рекомендации Марины на общую почту (владелец 06.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: ПК Альянс вручную)"))
