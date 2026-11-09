# -*- coding: utf-8 -*-
"""Владелец 09.11: «Темрон» — московское подразделение (msk@) направило на производство; пишем omts@temron.ru ответом в тред письма 42171; текст утверждён владельцем. [--katit]"""
import sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "2224176766", "omts@temron.ru", 42171
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
mb, rfc, thr, subj = st._conn.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
ТЕКСТ = """Добрый день!

Меня зовут Вячеслав, я из Компрессор Центра. Писал в московское подразделение ТЕМРОН, коллеги подсказали обращаться напрямую на производство, поэтому пишу вам.

На производстве котельного оборудования сжатый воздух идёт на пескоструйную подготовку, окраску и пневмоинструмент на сборке. Если на следующий год в планах есть компрессоры, осушка или модернизация компрессорной, готовы посчитать варианты. Мы сами производители: свой бренд Enger и собственные модульные компрессорные станции.

Подскажите, к кому у вас можно обратиться по этому вопросу? Буду благодарен, если перешлёте письмо главному механику или энергетику."""
print("с", mb, "→", КОМУ, "| тема:", subj, "| in-reply-to:", bool(rfc))
if "--katit" in sys.argv:
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=subj, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "temron-42171", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "Темрон: по указанию московского офиса на производство (владелец 09.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Темрон вручную)"))
