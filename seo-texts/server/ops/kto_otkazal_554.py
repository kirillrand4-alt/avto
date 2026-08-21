# -*- coding: utf-8 -*-
"""Кто именно отказал: наш релей на отправке или сервер получателя.

Владелец смотрит постмастер mail.ru - там доставляемость 100%. Это не
противоречие, но проверить надо: если 554 прилетает от НАШЕГО релея
(Яндекс 360, через который стоят все ящики), письмо до mail.ru не доезжает
вовсе и в постмастере его нет. Признак - домены получателей у отказов
РАЗНЫЕ: сервер получателя не может отказать за чужой домен.

Заодно смотрим ящики прямо сейчас: подбор только что не дал ни одного.
"""
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                    # noqa: E402
from sender.store import Store                                      # noqa: E402
from sender.wiring import build_deps                                # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT m.id, COALESCE(m.last_error,'') err, COALESCE(cr.email, r.email) email "
    "  FROM messages m LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    "  LEFT JOIN recipients r ON r.id=m.recipient_id "
    " WHERE COALESCE(m.last_error,'') LIKE '%554%' "
    "   AND COALESCE(m.last_error,'') LIKE '%suspicion of SPAM%'").fetchall()
дом = Counter(str(р["email"] or "").split("@")[-1].lower() for р in ряды)
print(f"отказов 554: {len(ряды)}; РАЗНЫХ доменов получателя: {len(дом)}")
for д, н in дом.most_common(12):
    print(f"  {н:>3}  {д}")
print("\nвывод: сервер получателя не отказывает за чужие домены -")
print("значит отказ пришёл от нашего релея на отправке.\n")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
cs = deps.confirm
живой = getattr(cs, "_sender", None)
сейчас = datetime.now(timezone.utc)
print(f"=== ящики на {сейчас:%H:%M} UTC ===")
for mb in cfg.mailboxes():
    ст = store.get_mailbox_state(mb.mailbox_id)
    рд = getattr(ст, "ramp_day", 0) if ст else 0
    ушло = getattr(ст, "sent_today", 0) if ст else 0
    пауза = getattr(ст, "paused", False) if ст else False
    лим = живой._daily_limit(mb.provider, рд, mb.mailbox_id)
    можно = живой.can_send_now(mb.mailbox_id, now=сейчас, manual=True)
    г = живой.gates.check_mailbox(mb.mailbox_id)
    гт = ("СРАБОТАЛ " + str(getattr(г, "reason", "") or "")[:44]) if г.tripped else "ок"
    print(f"{mb.mailbox_id:<42} {str(mb.division):<6} {ушло:>4}/{лим:<5} "
          f"пауза={'ДА' if пауза else 'нет':<4} можно={str(можно):<6} {гт}")

строка = cs.get(3413)
print(f"\nкарточка #3413 {строка.get('email')} ИНН {строка.get('inn')}")
cards = cs._cards
акт = getattr(cards, "active", False) if cards else False
print(f"  индекс активен: {акт}")
if акт:
    g = getattr(cards, "divisions", None)
    print(f"  направления компании: "
          f"{g(строка.get('inn')) if callable(g) else cards.division(строка.get('inn'))}")
print(f"  letter_division: {cs.letter_division(строка)}")
print(f"  _fallback_mailbox(meyer) -> {cs._fallback_mailbox(inn=строка.get('inn'), prefer_division='meyer')!r}")
