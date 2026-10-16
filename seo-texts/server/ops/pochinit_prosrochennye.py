# -*- coding: utf-8 -*-
"""Просроченные письма (владелец 16.10: «почини просроченные»).
* scheduled/approved с прошедшим сроком, если этому адресу письмо УЖЕ ушло
  (send_log sent) — дубль, ставим skipped;
* sending старше часа без записи в send_log — зависший захват, возвращаем в
  scheduled на «сейчас», автоотправка возьмёт заново.
Без --primenit — только счёт. Журнал — _ops/pochinit-prosrochennye.jsonl."""
import io
import json
import sqlite3
import sys
from datetime import datetime, timedelta

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
сейчас = datetime.utcnow()
теперь = сейчас.strftime("%Y-%m-%dT%H:%M:%S.%f")
ушло = {str(r[0]).lower() for r in c.execute("SELECT email FROM send_log WHERE outcome='sent'")}
дубли, зависшие, прочие = [], [], []
for mid, st, sa, em in c.execute(
        "SELECT m.id, m.status, COALESCE(m.claimed_at, m.scheduled_at), r.email FROM messages m "
        "JOIN recipients r ON r.id=m.recipient_id WHERE m.status IN ('scheduled','approved','sending')").fetchall():
    try:
        t = datetime.fromisoformat(str(sa).replace(" ", "T")[:19])
    except Exception:  # noqa: BLE001
        continue
    if st == "sending":
        if t < сейчас - timedelta(hours=1) and str(em).lower() not in ушло:
            зависшие.append(mid)
        continue
    if t > сейчас - timedelta(minutes=30):
        continue
    (дубли if str(em).lower() in ушло else прочие).append(mid)
print("дубли (адресу уже ушло):", len(дубли), "| зависшие в отправке:", len(зависшие), "| прочие просроченные:", прочие)
if "--primenit" in sys.argv:
    with c, io.open(r"C:\sender\_ops\pochinit-prosrochennye.jsonl", "a", encoding="utf-8") as ж:
        for m in дубли:
            c.execute("UPDATE messages SET status='skipped', last_error='дубль: адресу уже отправлено', updated_at=? "
                      "WHERE id=? AND status IN ('scheduled','approved')", (теперь, m))
            ж.write(json.dumps({"id": m, "bylo": "scheduled", "stalo": "skipped"}) + "\n")
        for m in зависшие:
            c.execute("UPDATE messages SET status='scheduled', claimed_at=NULL, scheduled_at=?, updated_at=? "
                      "WHERE id=? AND status='sending'", (теперь, теперь, m))
            ж.write(json.dumps({"id": m, "bylo": "sending", "stalo": "scheduled"}) + "\n")
    print("применено")
