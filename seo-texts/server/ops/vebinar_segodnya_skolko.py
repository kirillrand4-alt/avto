# -*- coding: utf-8 -*-
"""Сколько вебинарных ушло СЕГОДНЯ и что за десять писем со статусом sent
при карточке pending (они были такими ещё до сегодняшнего прогона)."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.status cst, cr.email, m.id mid, m.status mst, "
    "       m.mailbox_id, substr(m.sent_at,1,16) когда, m.subject "
    "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.dedup_key LIKE 'vebinar28:%' AND m.status='sent' "
    " ORDER BY m.sent_at"
).fetchall()
print(f"вебинарных писем со статусом sent: {len(ряды)}")
по_дням = Counter(str(р["когда"])[:10] for р in ряды)
print("по дням отправки:", dict(sorted(по_дням.items())))
print("\nте, что НЕ сегодня (карточка/письмо/тема):")
for р in ряды:
    if str(р["когда"])[:10] != "2026-08-21":
        print(f"  №{р['id']} карточка={р['cst']} {р['email']} {р['когда']} "
              f"<- {р['mailbox_id']}")
        print(f"       {str(р['subject'])[:70]}")
