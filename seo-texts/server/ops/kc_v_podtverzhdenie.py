# -*- coding: utf-8 -*-
"""Все запланированные письма КЦ — обратно в «Подтвердить отправку» (владелец
16.10: «перекинь в панель подтверждения все письма для кц»). Письмо scheduled/
approved -> pending_review, карточка approved -> pending. Журнал —
_ops/kc-v-podtverzhdenie.jsonl. Без --primenit — только счёт."""
import io
import json
import sqlite3
import sys
from datetime import datetime

КАМП_КЦ = (1, 5, 6, 10, 15, 16)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
т = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")
ряды = c.execute("SELECT id, status, scheduled_at FROM messages WHERE status IN ('scheduled','approved') "
                 "AND campaign_id IN (%s)" % ",".join(map(str, КАМП_КЦ))).fetchall()
print("писем КЦ в отправке:", len(ряды))
if "--primenit" in sys.argv:
    n = 0
    with c, io.open(r"C:\sender\_ops\kc-v-podtverzhdenie.jsonl", "a", encoding="utf-8") as ж:
        for mid, st, sa in ряды:
            c.execute("UPDATE messages SET status='pending_review', claimed_at=NULL, updated_at=? "
                      "WHERE id=? AND status IN ('scheduled','approved')", (т, mid))
            c.execute("UPDATE confirm_reviews SET status='pending', decided_by=NULL, decided_at=NULL, updated_at=? "
                      "WHERE message_id=? AND status='approved'", (т, mid))
            ж.write(json.dumps({"id": mid, "bylo": st, "scheduled_at": sa}) + "\n")
            n += 1
    print("переведено в подтверждение:", n)
    print("осталось в отправке:", c.execute(
        "SELECT COUNT(*) FROM messages WHERE status IN ('scheduled','approved','sending') AND campaign_id IN (%s)"
        % ",".join(map(str, КАМП_КЦ))).fetchone()[0])
