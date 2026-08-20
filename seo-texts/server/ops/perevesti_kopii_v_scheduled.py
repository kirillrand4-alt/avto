# -*- coding: utf-8 -*-
"""Письма одобренных копий - из pending_review в scheduled.

_ensure_message заводит письмо в pending_review (режим подтверждения), а
статус в scheduled переводит confirm_decide в момент одобрения. Наши
карточки были одобрены РАНЬШЕ, чем у них появилось письмо, и второй раз
решение не принимается - оно неизменно. Переводим сами, но только там,
где карточка действительно одобрена.
"""
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc).isoformat()

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id rid, cr.email, m.id mid, m.status mst, "
    "       substr(m.scheduled_at,1,16) slot, rc.company_name "
    "FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    "LEFT JOIN recipients rc ON rc.id=cr.recipient_id "
    "WHERE cr.status IN ('approved','edited') "
    "AND m.status='pending_review'").fetchall()
print(f"одобренных карточек с письмом в pending_review: {len(ряды)}")
for r in ряды:
    print(f"  #{r['rid']} {str(r['company_name'])[:28]:<28} письмо {r['mid']} "
          f"слот {r['slot']} {r['email']}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить - --katit")
    raise SystemExit(0)

n = 0
with store._lock:
    for r in ряды:
        store._conn.execute(
            "UPDATE messages SET status='scheduled', claimed_at=NULL, "
            "updated_at=? WHERE id=? AND status='pending_review'",
            (сейчас, int(r["mid"])))
        n += 1
    store._conn.commit()
print(f"\nпереведено в scheduled: {n}")
