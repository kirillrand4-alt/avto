# -*- coding: utf-8 -*-
"""Живые письма кампаний КЦ (10, 15) по статусам; с --snyat переводит их и карточки в skipped."""
import sqlite3, sys, time
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
Ж = "('scheduled','approved','pending_review','sending')"
for r in c.execute("SELECT campaign_id, status, COUNT(*) FROM messages WHERE campaign_id IN (10,15) AND status IN %s GROUP BY 1,2" % Ж): print(r)
if "--snyat" in sys.argv:
    т = time.strftime("%Y-%m-%dT%H:%M:%S"); п = "старый шаблон КЦ: снят по команде владельца 15.10"
    with c:
        мид = [r[0] for r in c.execute("SELECT id FROM messages WHERE campaign_id IN (10,15) AND status IN ('scheduled','approved','pending_review','sending')")]
        for m in мид:
            c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=?", (п, т, m))
            c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE message_id=? AND status IN ('pending','approved','edited')", (п, т, т, m))
    print("снято:", len(мид))
