# -*- coding: utf-8 -*-
"""Почему входящее 446320 не привязалось: заголовки ответа и наши письма этому адресу (только чтение)."""
import json, sqlite3
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
д = json.loads(c.execute("SELECT detail_json FROM events WHERE id=446320").fetchone()[0])
з = д.get("headers") or {}
for к in ("From", "To", "Subject", "In-Reply-To", "References", "Date"): print(к, "=", str(з.get(к, ""))[:200])
print("прочие ключи:", [к for к in д if к != "headers"], {к: str(д[к])[:200] for к in д if к not in ("headers",)})
адрес = "giga004@mail.ru"
print("наши письма на адрес:", c.execute("SELECT m.id, m.campaign_id, m.status, m.sent_at, m.mailbox_id, m.rfc_message_id FROM messages m JOIN recipients r ON r.id=m.recipient_id WHERE lower(r.email)=?", (адрес,)).fetchall())
print("получатель в базе:", c.execute("SELECT id, inn, company FROM recipients WHERE lower(email)=?", (адрес,)).fetchall() if "company" in [x[1] for x in c.execute("PRAGMA table_info(recipients)")] else c.execute("SELECT id, inn FROM recipients WHERE lower(email)=?", (адрес,)).fetchall())
print("письма с ящика a.miroshnichenko сегодня:", c.execute("SELECT COUNT(*) FROM messages WHERE mailbox_id='a.miroshnichenko@optic-sort.ru' AND sent_at>='2026-11-11'").fetchone()[0])
