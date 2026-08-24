# -*- coding: utf-8 -*-
"""Выборка писем целиком — читать глазами, а не считать счётчиком.

Владелец 24.08: «займись проверкой писем». Счётчик брака говорит, сколько
отсеяли, но не говорит, что прошло. Все три поломки 17-20.08 нашлись
именно глазами: письмо про компрессоры в магазин постельного белья,
четыре письма подряд с одинаковым зачином «Смотрел профиль», реклама
вместо вопроса.

Берём подряд идущий кусок сегодняшних писем — и ушедших, и ждущих в
очереди, — печатаем тему и тело как есть. Размер куска маленький нарочно:
панель отдаёт только хвост вывода, и десять писем в него не влезут.

    python zapusk_svoego_skripta.py ops/pisma_glazami.py [сдвиг] [сколько]
"""
import sqlite3
import sys

СДВИГ = int(sys.argv[1]) if len(sys.argv) > 1 else 0
СКОЛЬКО = int(sys.argv[2]) if len(sys.argv) > 2 else 4

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

строки = c.execute(
    "SELECT m.id, m.status, m.mailbox_id, m.sent_at, m.subject, "
    "       m.body_rendered, r.email, r.inn, r.company_name, r.okved "
    "  FROM messages m LEFT JOIN recipients r ON r.id=m.recipient_id "
    " WHERE substr(COALESCE(m.sent_at, m.created_at),1,10)=date('now') "
    "   AND m.body_rendered IS NOT NULL AND m.body_rendered<>'' "
    " ORDER BY m.id DESC LIMIT ? OFFSET ?", (СКОЛЬКО, СДВИГ)).fetchall()

print("писем в выборке: %d (сдвиг %d)\n" % (len(строки), СДВИГ))
for р in строки:
    print("=" * 78)
    print("#%s | %s | ящик %s | %s"
          % (р["id"], р["status"], str(р["mailbox_id"] or "?"),
             str(р["sent_at"] or "не отправлено")[:16]))
    print("кому: %s | ИНН %s | %s"
          % (str(р["email"] or "?"), р["inn"], str(р["company_name"] or "")[:44]))
    print("ОКВЭД: %s" % str(р["okved"] or "—")[:60])
    print("-" * 78)
    print("ТЕМА: %s" % р["subject"])
    print()
    тело = str(р["body_rendered"] or "")
    print(тело[:2200])
    if len(тело) > 2200:
        print("... (ещё %d знаков)" % (len(тело) - 2200))
    print()
