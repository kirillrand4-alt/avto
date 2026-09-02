# -*- coding: utf-8 -*-
"""Только чтение: в какие компании ушло по несколько писем вебинара.
Ответы (reply:) исключаем — это не рассылка."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
ПУБЛ = ("mail.ru", "gmail.com", "yandex.ru", "list.ru", "bk.ru", "inbox.ru",
        "ya.ru", "rambler.ru", "icloud.com", "yahoo.com", "outlook.com", "mail.com")

ряды = list(c.execute(
    "SELECT r.email, r.domain, r.inn, r.company_name, m.mailbox_id,"
    " substr(m.sent_at,12,5) когда FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=12 AND m.status='sent'"
    " AND m.idempotency_key NOT LIKE 'reply:%'"))
print("исходных писем рассылки (без ответов): %d" % len(ряды))

по_домену = {}
for р in ряды:
    if р["domain"] in ПУБЛ:
        continue
    по_домену.setdefault(р["domain"], []).append(р)
много = {д: с for д, с in по_домену.items() if len(с) > 1}
писем = sum(len(с) for с in много.values())
print("\n=== КОМПАНИЙ, ГДЕ ПИСЬМО ПОЛУЧИЛИ НЕСКОЛЬКО ЧЕЛОВЕК: %d ===" % len(много))
print("    писем в них: %d из %d" % (писем, len(ряды)))
for д, с in sorted(много.items(), key=lambda x: -len(x[1])):
    им = next((str(x["company_name"]) for x in с if x["company_name"]), д)
    print("\n  %-24s %-26s %d писем" % (д[:24], им[:26], len(с)))
    for x in с:
        print("      %-34s %s  с ящика %s"
              % (x["email"][:34], x["когда"], str(x["mailbox_id"]).split("@")[0]))

print("\n=== ОДИН ЧЕЛОВЕК ПОД ДВУМЯ АДРЕСАМИ ===")
норм = {}
for р in ряды:
    л, _, д = р["email"].partition("@")
    к = л.replace(".", "").replace("_", "").replace("-", "") + "@" + д
    норм.setdefault(к, []).append(р["email"])
for к, сп in норм.items():
    if len(set(сп)) > 1:
        print("  %s  <- один и тот же человек получил два письма" % ", ".join(set(сп)))
