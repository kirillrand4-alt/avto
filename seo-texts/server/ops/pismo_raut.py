# -*- coding: utf-8 -*-
"""Владелец 09.11: «Раут» — Кулагина (com1@) направила к коммерческому директору Сушкову С.А. com6@raut.pro. Ответом в тред письма 42400; текст утверждён владельцем. [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "5010026230", "com6@raut.pro", 42400
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
mb, rfc, thr, subj = st._conn.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
ТЕКСТ = """Сергей Алексеевич, добрый день!

Меня зовут Кирилл, я из Компрессор Центра. Светлана Николаевна Кулагина подсказала, что такие вопросы решаете вы, поэтому пишу напрямую.

Сейчас предприятия закладывают модернизацию и бюджеты на следующий год. Если в планах есть компрессорная, замена или добавление компрессоров, осушителей, ресиверов, посчитаем варианты: от винтовых до центробежных. Мы сами производители: свой бренд Enger и собственное производство модульных компрессорных станций, обслуживаем то, что ставим.

Подскажите, есть ли у вас сейчас такие задачи? Если удобнее, чтобы я связался с главным механиком или энергетиком, дайте, пожалуйста, контакт."""
print("с", mb, "→", КОМУ, "| тема:", subj, "| in-reply-to:", bool(rfc))
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "raut-42400", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "Раут: по рекомендации Кулагиной к Сушкову (владелец 09.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Раут вручную)"))
