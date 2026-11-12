# -*- coding: utf-8 -*-
"""Приостановить автоотправку кампании: письма в расписании (status='scheduled') → 'paused' (цикл автоотправки берёт
только 'scheduled'; перенос даты не годится — подтяжка под окно вернёт письмо назад). Обратимо: --vernut возвращает
'scheduled' ровно тем письмам, что были поставлены на паузу (журнал _ops/pauza-kampanii.jsonl).
Владелец 12.11: «приостанови их отправку» (кампания 13 «Второе касание — Meyer», 3 из 4 отказов Яндекса «спам»).
    pauza_kampanii.py <id кампании> [--primenit | --vernut]"""
import io, json, os, sqlite3, sys, time
from datetime import datetime, timezone
кам = int(sys.argv[1]); ЖУР = r"C:\sender\_ops\pauza-kampanii.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60); c.execute("PRAGMA busy_timeout=60000")
print("кампания:", c.execute("SELECT id, name, status FROM campaigns WHERE id=?", (кам,)).fetchone())
print("сообщения до:", c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=? GROUP BY status", (кам,)).fetchall())
т = datetime.now(timezone.utc).isoformat(timespec="seconds")
if "--primenit" in sys.argv:
    ids = [r[0] for r in c.execute("SELECT id FROM messages WHERE campaign_id=? AND status='scheduled'", (кам,))]
    c.execute("UPDATE messages SET status='paused', updated_at=? WHERE campaign_id=? AND status='scheduled'", (т, кам)); c.commit()
    with io.open(ЖУР, "a", encoding="utf-8") as ф:
        ф.write(json.dumps({"kampaniya": кам, "deystvie": "pauza", "ids": ids, "ts": т}, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
    print("на паузу:", len(ids))
elif "--vernut" in sys.argv:
    ids = []
    for с in io.open(ЖУР, encoding="utf-8"):
        з = json.loads(с)
        if з["kampaniya"] == кам and з["deystvie"] == "pauza": ids += з["ids"]
    n = 0
    for i in ids: n += c.execute("UPDATE messages SET status='scheduled', updated_at=? WHERE id=? AND status='paused'", (т, i)).rowcount
    c.commit()
    with io.open(ЖУР, "a", encoding="utf-8") as ф:
        ф.write(json.dumps({"kampaniya": кам, "deystvie": "vernut", "n": n, "ts": т}, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
    print("возвращено в расписание:", n)
print("сообщения после:", c.execute("SELECT status, COUNT(*) FROM messages WHERE campaign_id=? GROUP BY status", (кам,)).fetchall())
