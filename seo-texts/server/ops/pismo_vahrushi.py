# -*- coding: utf-8 -*-
"""Владелец 03.11: «Вахруши-Юфть» (snab@vaxrushi.ru) перенаправили к Екатерине Николаевне,
vuft_kirov@mail.ru — письмо от того же менеджера по имени, со ссылкой на переадресацию,
в тред первого письма (цитата прикладывается отправкой). Владелец: «отправь вручную».
    pismo_vahrushi.py [--katit]"""
import json, sys
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ = "4329014050", "vuft_kirov@mail.ru", 26351
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = st._conn
mb, rfc, thr, subj, body = c.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject, body_rendered FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
print("ящик:", mb, "| тема:", subj)
print("--- первое ---\n" + (body or "")[:2500])
print("--- уже писали на адрес:", c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE lower(email)=?", (КОМУ,)).fetchone()[0],
      c.execute("SELECT COUNT(*) FROM recipients r JOIN messages m ON m.recipient_id=r.id WHERE lower(r.email)=?", (КОМУ,)).fetchone()[0])
print("лиды:", c.execute("SELECT id, status FROM leads WHERE recipient_id IN (SELECT id FROM recipients WHERE inn=?)", (ИНН,)).fetchall())
print("статусы лидов:", c.execute("SELECT status, COUNT(*) FROM leads GROUP BY 1").fetchall())
for r in c.execute("SELECT id, status, decided_at, subject, substr(COALESCE(edited_body, body),1,400) FROM confirm_reviews WHERE lower(email)=?", (КОМУ,)):
    print("карточка", tuple(r))
for r in c.execute("SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.subject FROM recipients r JOIN messages m ON m.recipient_id=r.id WHERE lower(r.email)=?", (КОМУ,)):
    print("письмо", tuple(r))
print("лид:", [tuple(r) for r in c.execute("SELECT id, status FROM leads WHERE recipient_id IN (SELECT id FROM recipients WHERE inn=?)", (ИНН,))])
print("статусы:", [tuple(r) for r in c.execute("SELECT status, COUNT(*) FROM leads GROUP BY 1")])
ТЕМА = "Вопрос по компрессорам в «Вахруши-Юфть»"
ТЕКСТ = """Екатерина Николаевна, добрый день!

Ваши коллеги из отдела снабжения «Вахруши-Юфть» подсказали, что вопросы по компрессорному оборудованию ведёте вы, и что тема для вас актуальна. Поэтому пишу вам напрямую, моё первое письмо ниже.

Подскажите, на каких участках у вас сейчас стоят компрессоры: отжим, сушка, окраска? И есть ли планы по обновлению или расширению парка? Если удобнее обсудить по телефону, напишите, когда вам можно позвонить."""
if "--katit" in sys.argv:
    from datetime import datetime, timezone
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=ТЕМА, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "vahrushi-26351", recipient_id=None, inn=ИНН,
                                  panel={"mailbox_id": mb, "vruchnuyu": "Вахруши-Юфть: переадресация от snab@ (владелец 03.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Вахруши вручную)"))
        with c:
            c.execute("UPDATE leads SET status='perepiska' WHERE id=746")
        print("лид 746 → perepiska")
else:
    print("\n=== ПИСЬМО ===\n" + ТЕКСТ)
