# -*- coding: utf-8 -*-
"""Найти компанию во всех очередях и отправках по кускам названия/домена/ИНН
(владелец 21.10: «проверить алтайэкосорт в отправках холодных писем»).
С --snyat — письма в работе (pending_review/scheduled/approved) и их карточки
-> skipped с причиной. Журнал — _ops/naiti-kompaniyu-vezde.jsonl.

    naiti_kompaniyu_vezde.py <кусок>,<кусок>,... ["причина"] [--snyat]"""
import io
import json
import sqlite3
import sys
import time

куски = [k for k in sys.argv[1].split(",") if k]
причина = next((a for a in sys.argv[2:] if not a.startswith("--")), "снято владельцем")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
кам = {r[0]: r[1] for r in c.execute("SELECT id, name FROM campaigns")}
усл = " OR ".join(["lower(company_name) LIKE ? OR lower(email) LIKE ? OR inn LIKE ?"] * len(куски))
пар = []
for к in куски:
    л = "%" + к.lower() + "%"
    пар += [л, л, л]
rids = c.execute("SELECT id, email, company_name, inn, segment FROM recipients WHERE " + усл, пар).fetchall()
print("получателей:", len(rids))
инн = {r[3] for r in rids if r[3]}
for r in rids:
    print("  #%s %s | %s | ИНН %s | %s" % r)
ids = [r[0] for r in rids]
if инн:
    ids += [r[0] for r in c.execute("SELECT id FROM recipients WHERE inn IN (%s)" % ",".join("?" * len(инн)), list(инн))
            if r[0] not in ids]
в_работе = []
if ids:
    q = ",".join("?" * len(ids))
    for m in c.execute("SELECT m.id, m.status, m.campaign_id, m.mailbox_id, m.sent_at, m.scheduled_at, r.email FROM messages m "
                       "JOIN recipients r ON r.id=m.recipient_id WHERE m.recipient_id IN (%s) ORDER BY m.id" % q, ids):
        print("  письмо #%s %-14s %-28s ящик %s ушло %s план %s -> %s" % (m[0], m[1], str(кам.get(m[2]))[:28], m[3], str(m[4])[:16], str(m[5])[:16], m[6]))
        if m[1] in ("pending_review", "scheduled", "approved"):
            в_работе.append(m[0])
    for k in c.execute("SELECT id, status, campaign_id, email FROM confirm_reviews WHERE recipient_id IN (%s)" % q, ids):
        print("  карточка #%s %s %s %s" % (k[0], k[1], кам.get(k[2]), k[3]))
    for л in c.execute("SELECT id, email, status, reply_kind FROM leads WHERE recipient_id IN (%s)%s" % (
            q, (" OR inn IN (%s)" % ",".join("?" * len(инн))) if инн else ""), ids + list(инн)):
        print("  лид", л)
print("send_log:", c.execute("SELECT COUNT(*) FROM send_log WHERE " + " OR ".join(["lower(email) LIKE ? OR inn LIKE ?"] * len(куски)),
                             sum([["%" + к.lower() + "%"] * 2 for к in куски], [])).fetchone()[0])
print("стоп-лист:", c.execute("SELECT value, reason FROM suppression WHERE " + " OR ".join(["lower(value) LIKE ?"] * len(куски)),
                              ["%" + к.lower() + "%" for к in куски]).fetchall()[:10])
print("в работе (не ушло):", в_работе)
if "--snyat" in sys.argv and в_работе:
    т = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c, io.open(r"C:\sender\_ops\naiti-kompaniyu-vezde.jsonl", "a", encoding="utf-8") as ж:
        for mid in в_работе:
            st = c.execute("SELECT status FROM messages WHERE id=?", (mid,)).fetchone()[0]
            c.execute("UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=?", (причина, т, mid))
            c.execute("UPDATE confirm_reviews SET status='skipped', updated_at=? WHERE message_id=? AND status IN ('pending','approved')", (т, mid))
            ж.write(json.dumps({"id": mid, "bylo": st, "prichina": причина}, ensure_ascii=False) + "\n")
    print("СНЯТО:", len(в_работе))
