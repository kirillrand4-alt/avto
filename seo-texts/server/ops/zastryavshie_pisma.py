# -*- coding: utf-8 -*-
"""Статусы писем и признаки застревания цикла отправки."""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)

with store._lock:
    по_статусу = store._conn.execute(
        "SELECT status, COUNT(*) FROM messages GROUP BY status "
        "ORDER BY 2 DESC").fetchall()
print("все письма по статусу:")
for с, n in по_статусу:
    print(f"  {с:<14} {n}")

with store._lock:
    зависшие = store._conn.execute(
        "SELECT id, status, claimed_at, scheduled_at, attempt_count, "
        "       substr(COALESCE(last_error,''),1,60) "
        "FROM messages WHERE status NOT IN ('sent','skipped','scheduled') "
        "ORDER BY updated_at DESC LIMIT 15").fetchall()
print(f"\nне sent/skipped/scheduled: {len(зависшие)}")
for r in зависшие:
    print(f"  #{r[0]} {r[1]:<10} claimed={str(r[2])[:19]} "
          f"попыток={r[4]} {r[5]}")

with store._lock:
    посл = store._conn.execute(
        "SELECT event_ts, mailbox_id FROM events WHERE event_type='sent' "
        "ORDER BY event_ts DESC LIMIT 5").fetchall()
print("\nпоследние отправки:")
for ts, mb in посл:
    прошло = (сейчас - datetime.fromisoformat(str(ts).replace("Z", "+00:00")
                                              )).total_seconds() / 60
    print(f"  {str(ts)[:19]}  {mb}  ({прошло:.0f} мин назад)")

# ближайшие scheduled_at у тех, чей срок «настал»
with store._lock:
    р = store._conn.execute(
        "SELECT scheduled_at, COUNT(*) FROM messages WHERE status='scheduled' "
        "GROUP BY substr(scheduled_at,1,13) ORDER BY scheduled_at LIMIT 10"
    ).fetchall()
print("\nscheduled_at у очереди (час -> писем):")
for ts, n in р:
    print(f"  {str(ts)[:16]}  {n}")
