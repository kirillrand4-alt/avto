# -*- coding: utf-8 -*-
"""Снять ВСЕ неотправленные карточки кампании (pending/approved) и их письма -> skipped с причиной. Журнал
_ops/snyato-kampaniya.jsonl (fsync).   snyat_kampaniyu.py <id кампании> "<причина>" [--primenit]"""
import io, json, os, sqlite3, sys, time
from collections import Counter
К = int(sys.argv[1]); ПР = sys.argv[2]; т = time.strftime("%Y-%m-%dT%H:%M:%S")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
print("кампания:", c.execute("SELECT id, name FROM campaigns WHERE id=?", (К,)).fetchone())
ряды = c.execute("SELECT id, message_id, status FROM confirm_reviews WHERE campaign_id=? AND status IN ('pending','approved')", (К,)).fetchall()
сообщ = Counter(r[0] for r in c.execute("SELECT m.status FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id WHERE cr.campaign_id=? AND cr.status IN ('pending','approved')", (К,)))
print("к снятию карточек %d %s | статусы писем %s" % (len(ряды), dict(Counter(r[2] for r in ряды)), dict(сообщ)))
if "--primenit" in sys.argv:
    with c, io.open(r"C:\sender\_ops\snyato-kampaniya.jsonl", "a", encoding="utf-8") as ж:
        for кид, mid, ст in ряды:
            c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=?", (ПР, т, т, кид))
            if mid: c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN ('pending_review','approved','scheduled')", (ПР, т, mid))
            ж.write(json.dumps({"kampaniya": К, "karta": кид, "message": mid, "bylo": ст, "ts": т}, ensure_ascii=False) + "\n")
        ж.flush(); os.fsync(ж.fileno())
    print("СНЯТО:", len(ряды))
