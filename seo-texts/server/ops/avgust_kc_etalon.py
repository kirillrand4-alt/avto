# -*- coding: utf-8 -*-
"""Августовские письма КЦ (владелец 19.10: «откопай первоначальные правила, по
которым писались письма»): отправленные КЦ по неделям, доля ответов людей,
и выгрузка всех августовских писем с пометкой «ответили» в
_ops/avgust-kc-pisma.json — эталон для восстановления канона. Только чтение."""
import io
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}


def кц(cid, mb):
    return "ompressor" in str(mb) or not any(w in str(кам.get(cid, "")).lower() for w in ("meyer", "мейер"))


ответ = {r[0] for r in c.execute("SELECT recipient_id FROM events WHERE event_type='reply'")}
кол = {r[1] for r in c.execute("PRAGMA table_info(messages)")}
тело = "body_rendered" if "body_rendered" in кол else "body"
тема = "subject_rendered" if "subject_rendered" in кол else "subject"
ряды = c.execute("SELECT m.id, m.campaign_id, m.mailbox_id, m.sent_at, m.recipient_id, m.%s, m.%s, r.email, r.company_name "
                 "FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE m.status='sent' AND m.sent_at < '2026-09-15'"
                 % (тема, тело)).fetchall()
нед, нед_о = Counter(), Counter()
выгр = []
for mid, cid, mb, sa, rid, su, bo, em, co in ряды:
    if not кц(cid, mb):
        continue
    from datetime import date
    d = date.fromisoformat(str(sa)[:10])
    к = "%s нед.%02d" % (str(sa)[:7], d.isocalendar()[1])
    нед[к] += 1
    if rid in ответ:
        нед_о[к] += 1
    выгр.append({"id": mid, "kamp": кам.get(cid, cid), "sent": str(sa)[:16], "email": em, "kompaniya": co,
                 "otvetili": rid in ответ, "tema": su, "telo": bo})
print("неделя | отправлено КЦ | ответили | %")
for к in sorted(нед):
    print("%-16s %5d %4d %5.1f%%" % (к, нед[к], нед_о[к], 100 * нед_о[к] / нед[к]))
ж = io.open(r"C:\sender\_ops\avgust-kc-pisma.json", "w", encoding="utf-8")
json.dump(выгр, ж, ensure_ascii=False)
ж.close()
print("выгружено писем:", len(выгр), "из них с ответом:", sum(1 for x in выгр if x["otvetili"]))
по_кам = Counter((x["kamp"], x["otvetili"]) for x in выгр)
for k in sorted({x["kamp"] for x in выгр}, key=str):
    print("  кампания %-34s отправлено %4d ответили %3d" % (str(k)[:34], по_кам[(k, False)] + по_кам[(k, True)], по_кам[(k, True)]))
