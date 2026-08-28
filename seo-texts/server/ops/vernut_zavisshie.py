# -*- coding: utf-8 -*-
"""Вернуть зависшие в sending письма в расписание на сегодняшнее окно.

Захвачены отправкой и брошены (attempt_count=0, ни sent_at, ни rfc, ни
события, ни строки в send_log) — значит SMTP к ним даже не подходил, и
повторной отправки быть не может.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
СЛЕД = r"C:\sender\_ops\vernuto-zavisshih.jsonl"

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
win = window_from(store, cfg)
now = datetime.now(timezone.utc)
print("окно: %s" % str(win)[:140])

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT m.id, m.recipient_id, m.scheduled_at, rc.email, rc.company_name, "
    "       cr.id crid, cr.status crst "
    "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
    "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
    " WHERE m.status='sending' AND m.attempt_count=0 AND m.sent_at IS NULL "
    "   AND m.rfc_message_id IS NULL ORDER BY m.scheduled_at").fetchall()
c.close()
print("зависших к возврату: %d" % len(строки))
сч = Counter(str(r["crst"] or "нет карточки") for r in строки)
print("   статус карточек: %s" % dict(сч))
if not КАТИТЬ:
    for r in строки[:6]:
        rec = store.get_recipient(int(r["recipient_id"]))
        слот = next_slot(win, recipient_tz_name(win, rec), now) if rec else None
        print("   msg %-6s %-26s было %s -> станет %s"
              % (r["id"], str(r["email"])[:26], str(r["scheduled_at"])[:16],
                 str(слот)[:16]))
    raise SystemExit(0)

итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8")
for r in строки:
    rec = store.get_recipient(int(r["recipient_id"])) if r["recipient_id"] else None
    if rec is None:
        итог["нет получателя"] += 1
        continue
    try:
        снят = store.release_message(int(r["id"]))
        слот = next_slot(win, recipient_tz_name(win, rec), now)
        store.reschedule_message(int(r["id"]), слот)
        итог["возвращено"] += 1
        поток.write(json.dumps({"msg": int(r["id"]), "email": r["email"],
                                "bylo": str(r["scheduled_at"]),
                                "stalo": str(слот), "lease": bool(снят)},
                               ensure_ascii=False) + "\n")
        поток.flush()
        os.fsync(поток.fileno())
    except Exception as ex:                                      # noqa: BLE001
        итог["ошибка: " + str(ex)[:44]] += 1
поток.close()
print("")
for к, n in итог.most_common():
    print("   %-34s %4d" % (к, n))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
print("осталось в sending: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sending'").fetchone()[0])
c.close()
