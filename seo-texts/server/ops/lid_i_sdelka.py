# -*- coding: utf-8 -*-
"""Лид + сделки Битрикса по его ИНН (sdelki_napr) + последние письма: lid_i_sdelka.py LEAD_ID. Только чтение."""
import json, sqlite3, sys
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
л = c.execute("SELECT id, email, inn, company_name, status, reply_kind, need, created_at, recipient_id FROM leads WHERE id=?", (int(sys.argv[1]),)).fetchone()
print("ЛИД:", л[:6], "| создан", л[7]); print("  что написал:", (л[6] or "")[:400].replace("\n", " "))
ц = "".join(ч for ч in str(л[2] or "") if ч.isdigit())
for r in c.execute("SELECT inn, meyer, kc, sc, detali, ts FROM sdelki_napr WHERE inn=?", (ц,)): print("СДЕЛКИ:", r[:4], "| выгрузка", r[5]); print("  ", str(r[4])[:900])
for r in c.execute("SELECT m.id, m.sent_at, m.mailbox_id, c.name, m.subject FROM messages m LEFT JOIN campaigns c ON c.id=m.campaign_id WHERE m.recipient_id=? AND m.status='sent' ORDER BY m.id", (л[8],)): print("НАШЕ:", r)
for r in c.execute("SELECT event_type, event_ts, mailbox_id, json_extract(detail_json,'$.snippet') FROM events WHERE recipient_id=? AND event_type IN ('reply','reply_auto') ORDER BY id", (л[8],)): print("ОТВЕТ:", r)
for r in c.execute("SELECT status, decided_at, COALESCE(edited_body, body) FROM confirm_reviews WHERE recipient_id=? AND kind='reply' ORDER BY id", (л[8],)): print("НАШ ОТВЕТ:", r)
