# -*- coding: utf-8 -*-
"""Вернуть в расписание письма, снятые заслоном автоотправки «уже писали».

Это копии на второй адрес; в auto_send есть ветка, которая для них сверяет
только адрес, а включается она словами «копия на второй адрес» в причине
карточки. Причина была другой — заслон сработал по ИНН.
"""
import io
import json
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ids = []
for с in io.open(r"C:\sender\_ops\v-avtootpravku.jsonl", encoding="utf-8"):
    d = json.loads(с)
    if "review" in d:
        ids.append(int(d["review"]))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(ids))
беда = c.execute(
    "SELECT cr.id, cr.email, cr.recipient_id, m.id mid, m.last_error "
    "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.id IN (%s) AND m.status='skipped' "
    "   AND COALESCE(m.last_error,'') LIKE 'auto_send:уже писали%%'" % зн,
    ids).fetchall()
c.close()
print("снято заслоном автоотправки: %d" % len(беда))
if not КАТИТЬ or not беда:
    for r in беда[:5]:
        print("   rev %-6s %-30s %s" % (r["id"], str(r["email"])[:30], r["last_error"]))
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.auto_send import next_slot, recipient_tz_name, window_from  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
win = window_from(store, cfg)
now = datetime.now(timezone.utc)
итог = Counter()
for r in беда:
    rec = store.get_recipient(int(r["recipient_id"])) if r["recipient_id"] else None
    if rec is None:
        итог["нет получателя"] += 1
        continue
    слот = next_slot(win, recipient_tz_name(win, rec), now)
    with store.transaction() as conn:
        conn.execute(
            "UPDATE confirm_reviews SET reason=?, updated_at=? WHERE id=?",
            ("bulk-to-auto: копия на второй адрес (судья: годно)",
             time.strftime("%Y-%m-%dT%H:%M:%S"), int(r["id"])))
        n = conn.execute(
            "UPDATE messages SET status='scheduled', last_error=NULL, "
            "       claimed_at=NULL, scheduled_at=?, updated_at=? "
            " WHERE id=? AND status='skipped'",
            (слот.isoformat(), time.strftime("%Y-%m-%dT%H:%M:%S"),
             int(r["mid"]))).rowcount
    итог["возвращено" if n else "письмо уже не skipped"] += 1
print("")
for к, n in итог.most_common():
    print("   %-30s %4d" % (к, n))
