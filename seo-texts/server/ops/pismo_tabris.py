# -*- coding: utf-8 -*-
"""Владелец 09.11 «делай»: Табрис (ТВК-Р) — напоминание в ветку письма 22908 на offer@tabris.ru
(16.10, ящик Бояркина), и снять дубль 22905 (pending_review с 16.10 на тот же offer@). [--katit]"""
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
ИНН, КОМУ, ПЕРВОЕ, ДУБЛЬ = "2310123447", "offer@tabris.ru", 22908, 22905
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db")); к = st._conn
mb, rfc, thr, subj, rid = к.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject, recipient_id FROM messages WHERE id=?", (ПЕРВОЕ,)).fetchone()
д = к.execute("SELECT id, status, lower((SELECT email FROM recipients WHERE id=recipient_id)) FROM messages WHERE id=?", (ДУБЛЬ,)).fetchone()
ТЕКСТ = """Добрый день!

Направлял вам 16 октября предложение по контролю посторонних включений в готовой продукции. Удалось ли ознакомиться?

Если удобно, бесплатно проверим образцы вашей продукции на тестовом оборудовании и покажем результат."""
тема = "Re: " + (subj or "").replace("Re: ", "")
print("с", mb, "→", КОМУ, "| тема:", тема, "| in-reply-to:", bool(rfc), "| дубль:", д)
if "--katit" in sys.argv:
    т = datetime.now(timezone.utc).isoformat()
    if д and д[1] == "pending_review" and д[2] == КОМУ:
        with st._lock:
            к.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status='pending_review'", ("дубль письма 22908 (владелец 09.11)", т, ДУБЛЬ))
            к.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE message_id=? AND status='pending'", ("дубль письма 22908 (владелец 09.11)", т, т, ДУБЛЬ))
            к.commit()
        print("дубль снят")
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to=КОМУ, subject=тема, body=ТЕКСТ, in_reply_to=rfc, thread_id=thr or "tabris-22908",
                                  recipient_id=rid, inn=ИНН, panel={"mailbox_id": mb, "vruchnuyu": "Табрис: напоминание о предложении (владелец 09.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Табрис напоминание)"))
