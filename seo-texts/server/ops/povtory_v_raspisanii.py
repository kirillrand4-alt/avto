# -*- coding: utf-8 -*-
"""Письма КЦ в расписании (scheduled/approved), чьей компании или адресу письмо
КЦ уже ушло меньше 30 дней назад (владелец 21.10: повторы КЦ <30 дней — снять).
С --snyat — такие письма -> skipped (карточка тоже), журнал
_ops/povtory-v-raspisanii.jsonl."""
import io
import json
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
кц = {k for k, v in кам.items() if k in (1, 5, 6, 9, 10) or "КЦ" in str(v or "")}
гр = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
недавно = {}
for i, e, cid, ts in c.execute("SELECT inn, lower(email), campaign_id, ts FROM send_log WHERE outcome='sent' AND ts>=?", (гр,)):
    if cid in кц:
        if i:
            недавно[("inn", str(i))] = (ts, кам.get(cid))
        недавно[("em", e)] = (ts, кам.get(cid))
сн = []
сч = Counter()
for mid, cid, st, inn, em in c.execute(
        "SELECT m.id, m.campaign_id, m.status, r.inn, lower(r.email) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status IN ('scheduled','approved') AND m.campaign_id IN (%s)" % ",".join(map(str, кц))):
    х = недавно.get(("em", em)) or недавно.get(("inn", str(inn)))
    if х:
        сн.append(mid)
        сч[("тот же адрес" if ("em", em) in недавно else "другой адрес компании", str(х[1]))] += 1
print("писем КЦ в расписании, повтор <30 дней:", len(сн), dict(сч))
if "--snyat" in sys.argv and сн:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c, io.open(r"C:\sender\_ops\povtory-v-raspisanii.jsonl", "a", encoding="utf-8") as ж:
        for mid in сн:
            c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN ('scheduled','approved')",
                      ("повтор КЦ <30 дней (владелец 21.10)", т, mid))
            c.execute("UPDATE confirm_reviews SET status='skipped', updated_at=? WHERE message_id=? AND status='approved'", (т, mid))
            ж.write(json.dumps({"id": mid, "ts": т}) + "\n")
    print("СНЯТО:", len(сн))
