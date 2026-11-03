# -*- coding: utf-8 -*-
"""Владелец 03.11: на ea@min-rz.ru уже писали (письмо 5165, 25.08, И. Бояркин) — снять
карточку 40526 и отправить напоминание в тот же тред с того же ящика (цитата первого
прикладывается отправкой). Владелец: «сделай и отправь сам». [--katit]"""
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
from sender.config import Config            # noqa: E402
from sender.store import Store              # noqa: E402
from sender.wiring import build_deps        # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
st = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = st._conn
mb, rfc, thr, subj, rid = c.execute("SELECT mailbox_id, rfc_message_id, thread_id, subject, recipient_id FROM messages WHERE id=5165").fetchone()
ТЕКСТ = """Добрый день!

Коллеги из «Фишландии» подсказали, что вопросы контроля качества решаете вы, поэтому возвращаюсь к своему письму от 25 августа (оно ниже).

Подскажите, как у вас сейчас проверяют готовую продукцию на посторонние включения? Рентген-инспекция Meyer находит металл, стекло, керамику, камень и силикон прямо в закрытой упаковке, в том числе в ведёрной фасовке. Если интересно, можем бесплатно проверить ваш образец на нашем оборудовании.

Буду благодарен за ответ."""
print("с", mb, "→ ea@min-rz.ru | Тема:", subj, "\n\n" + ТЕКСТ)
if "--katit" in sys.argv:
    т = datetime.now(timezone.utc).isoformat()
    with c:
        c.execute("UPDATE confirm_reviews SET status='skipped', reason='заменена напоминанием в тред 5165', decided_at=?, updated_at=? WHERE id=40526 AND status='pending'", (т, т))
    deps = build_deps(cfg, st, dry_run=False)
    р = deps.confirm.submit_reply(reply_to="ea@min-rz.ru", subject=subj, body=ТЕКСТ, in_reply_to=rfc,
                                  thread_id=thr or "fishlandiya-5165", recipient_id=rid, inn="2455042689",
                                  panel={"mailbox_id": mb, "vruchnuyu": "Фишландия: напоминание в тред 5165 (владелец 03.11)"})
    print("карточка", р.review_id, р.status, р.created)
    if р.status == "pending":
        print("отправка:", deps.confirm.approve(р.review_id, operator="kirill (через Claude: Фишландия вручную)"))
