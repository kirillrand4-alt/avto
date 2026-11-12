# -*- coding: utf-8 -*-
"""Что за входящее от ooo_turksad@mail.ru на e.kuznetsova@rentgen-control.ru 12.11 (в панели «автоответ клиента», текст «письмо»):
заголовки, тип, сниппет; наше письмо, на которое ответ. Только чтение."""
import json, sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
for eid, тип, ts, mid, rid, dj in c.execute("SELECT id, event_type, event_ts, message_id, recipient_id, detail_json FROM events WHERE mailbox_id='e.kuznetsova@rentgen-control.ru' "
                                           "AND event_ts>='2026-11-11' AND detail_json LIKE '%turksad%'"):
    д = json.loads(dj or "{}"); з = д.get("headers") or {}
    print("событие", eid, тип, ts, "письмо", mid, "получатель", rid)
    for к in ("From", "To", "Subject", "Content-Type", "X-Mailer", "In-Reply-To", "Auto-Submitted", "X-Autoreply", "Precedence"):
        if з.get(к): print("   %s: %s" % (к, str(з[к])[:160]))
    print("   kind:", д.get("kind"), "| reply_kind:", д.get("reply_kind"), "| ключи:", list(д.keys()))
    print("   сниппет:", repr(str(д.get("snippet"))[:400]))
    if mid:
        print("   наше письмо:", c.execute("SELECT campaign_id, mailbox_id, sent_at, subject, COALESCE(in_reply_to,'')<>'' FROM messages WHERE id=?", (mid,)).fetchone())
