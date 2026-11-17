# -*- coding: utf-8 -*-
"""Владелец 17.11: «отмени свои 8 переписанных… сними 8 эти лучше». Карточки писем с ruchnaya_pravka в кампании
«Meyer провалы 17.11» → skipped; в журнал партии — запись status «снято владельцем», чтобы завод их не вернул.
    meyer_snyat_ruchnye_1711.py [--primenit]"""
import io, json, os, sqlite3, sys, time
ж = r"C:\sender\_ops\meyer-partiya.jsonl"; т = time.strftime("%Y-%m-%dT%H:%M:%S"); ПР = "снято владельцем 17.11 (ручные правки отменены)"
посл = {}
for с in io.open(ж, encoding="utf-8"):
    if с.strip(): з = json.loads(с); посл[з["kluch"]] = з
руч = [з for з in посл.values() if з.get("ruchnaya_pravka") and з.get("status") == "ок"]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
К = c.execute("SELECT id FROM campaigns WHERE name='Meyer провалы 17.11'").fetchone()[0]
карт = []
for з in руч:
    for кид, mid, ст in c.execute("SELECT id, message_id, status FROM confirm_reviews WHERE campaign_id=? AND lower(email)=? AND status IN ('pending','approved')", (К, з["email"].lower())):
        карт.append((кид, mid, з["kluch"], з.get("kompaniya")))
print("ручных записей %d, карточек к снятию %d:" % (len(руч), len(карт)), [(к[0], к[3]) for к in карт])
if "--primenit" in sys.argv:
    with c:
        for кид, mid, _, _ in карт:
            c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, decided_at=?, updated_at=? WHERE id=?", (ПР, т, т, кид))
            if mid: c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? AND status IN ('pending_review','approved','scheduled')", (ПР, т, mid))
    with io.open(ж, "a", encoding="utf-8") as ф:
        for з in руч: ф.write(json.dumps(dict(з, status="снято владельцем", ts=т), ensure_ascii=False) + "\n")
        ф.flush(); os.fsync(ф.fileno())
    print("СНЯТО карточек %d, записей в журнал %d" % (len(карт), len(руч)))
