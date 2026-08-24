# -*- coding: utf-8 -*-
"""Завёлся ли лид по ответу «Агропродукта» и на какой адрес он смотрит.

Человек ответил с личного адреса и прямо попросил слать предложения ему.
Если карточка лида смотрит на общий office@, продавец ответит не туда.
"""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
колонки = [р[1] for р in c.execute("PRAGMA table_info(leads)")]
print("колонки leads:", ", ".join(колонки), "\n")

for р in c.execute(
        "SELECT * FROM leads WHERE COALESCE(inn,'')='3905029996' "
        "   OR lower(COALESCE(email,'')) IN "
        "      ('vs@koenigsauce.ru','office@koenigsauce.ru') "
        " ORDER BY id DESC LIMIT 5"):
    д = dict(р)
    print(f"лид #{д.get('id')}:")
    for к in ("inn", "email", "company_name", "status", "kind", "source",
              "created_at", "updated_at", "last_message_at", "note"):
        if к in д and д.get(к) not in (None, ""):
            print(f"   {к:<16}: {str(д.get(к))[:100]}")
    print()

print("=== события по этой компании ===")
for р in c.execute(
        "SELECT e.id, e.event_type, substr(COALESCE(e.event_ts,e.created_at),1,19) когда, "
        "       e.mailbox_id, r.email "
        "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE r.inn='3905029996' ORDER BY e.id DESC LIMIT 10"):
    print(f"  #{р['id']:<7} {р['event_type']:<10} {р['когда']} "
          f"{str(р['mailbox_id'] or '-'):<32} {р['email']}")

print("\n=== ответы, которые ждут реакции (последние) ===")
for р in c.execute(
        "SELECT e.id, substr(COALESCE(e.event_ts,e.created_at),1,19) когда, "
        "       e.mailbox_id, r.company_name, r.email "
        "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='reply' ORDER BY e.id DESC LIMIT 12"):
    print(f"  #{р['id']:<7} {р['когда']} {str(р['company_name'] or '?')[:28]:<28} "
          f"{р['email']}")
