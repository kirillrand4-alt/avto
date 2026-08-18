# -*- coding: utf-8 -*-
"""Точная копия условия claim_approved_due, без изменения статусов.

Разница с «наивным» JOIN важна: claim берёт ПОСЛЕДНЮЮ строку ревью по письму
(cr.id DESC LIMIT 1). Если письму позже завели новое ревью в статусе
pending, письмо для цикла невидимо, хотя старое ревью и одобрено.
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc).isoformat()

with store._lock:
    точно = store._conn.execute(
        """SELECT COUNT(*) FROM messages m
            WHERE m.status='scheduled' AND m.scheduled_at <= ?
              AND (SELECT cr.status FROM confirm_reviews cr
                    WHERE cr.message_id=m.id
                    ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')""",
        (сейчас,)).fetchone()[0]
    наивно = store._conn.execute(
        "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
        "ON c.message_id=m.id WHERE m.status='scheduled' "
        "AND c.status IN ('approved','edited') AND m.scheduled_at<=?",
        (сейчас,)).fetchone()[0]
    последние = store._conn.execute(
        """SELECT (SELECT cr.status FROM confirm_reviews cr
                    WHERE cr.message_id=m.id ORDER BY cr.id DESC LIMIT 1) s,
                  COUNT(*) FROM messages m
            WHERE m.status='scheduled' AND m.scheduled_at <= ?
            GROUP BY s""", (сейчас,)).fetchall()
    многоревью = store._conn.execute(
        """SELECT COUNT(*) FROM (SELECT cr.message_id FROM confirm_reviews cr
             JOIN messages m ON m.id=cr.message_id
            WHERE m.status='scheduled' AND cr.message_id IS NOT NULL
            GROUP BY cr.message_id HAVING COUNT(*)>1)""").fetchone()[0]

print(f"условие claim_approved_due (последнее ревью): {точно}")
print(f"наивный JOIN (любое ревью):                   {наивно}")
print(f"писем очереди с несколькими ревью:            {многоревью}")
print("\nпоследнее ревью у писем, чей срок настал:")
for s, n in последние:
    print(f"  {str(s):<14} {n}")
