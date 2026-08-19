# -*- coding: utf-8 -*-
"""Разобрать конкретный дубль: два письма на один адрес.

Смотрим оба письма целиком: кампания, направление, ящик, тема, зачин. Надо
понять, это два независимых касания по двум направлениям (компания подходит
обоим) или письмо ушло с чужого ящика.
"""
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

АДРЕС = sys.argv[1] if len(sys.argv) > 1 else "zakupka@syrodelovo.ru"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def _т(s, n=500):
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


with store._lock:
    письма = store._conn.execute(
        "SELECT m.id, m.campaign_id, m.sent_at, m.mailbox_id, m.subject, "
        "       m.body_rendered, r.company_name, r.inn, r.segment "
        "FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
        "WHERE lower(r.email)=? AND m.status='sent' ORDER BY m.sent_at",
        (АДРЕС.lower(),)).fetchall()

print(f"== {АДРЕС}: писем {len(письма)} ==")
for p in письма:
    print(f"\n--- #{p['id']} кампания {p['campaign_id']} "
          f"{str(p['sent_at'])[:16]} ---")
    print(f"  ЯЩИК: {p['mailbox_id']}")
    print(f"  ТЕМА: {p['subject']}")
    print(f"  {_т(p['body_rendered'], 400)}")

print(f"\nкомпания: {письма[0]['company_name'] if письма else '—'} "
      f"| ИНН {письма[0]['inn'] if письма else '—'} "
      f"| сегмент базы: {письма[0]['segment'] if письма else '—'}")

print("\n== направления ящиков ==")
for mb in cfg.mailboxes():
    if mb.mailbox_id in {str(p["mailbox_id"]) for p in письма}:
        print(f"  {mb.mailbox_id}: направление "
              f"{getattr(mb, 'division', '—')}, пул {getattr(mb,'pool','—')}")
