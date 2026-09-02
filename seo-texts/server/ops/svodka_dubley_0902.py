# -*- coding: utf-8 -*-
"""Только чтение: короткая сводка по повторам внутри вебинара."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
ПУБЛ = ("mail.ru", "gmail.com", "yandex.ru", "list.ru", "bk.ru", "inbox.ru",
        "ya.ru", "rambler.ru", "icloud.com", "yahoo.com", "outlook.com", "mail.com")
ряды = list(c.execute(
    "SELECT r.email, r.domain, r.company_name FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id=12"
    " AND m.status='sent' AND m.idempotency_key NOT LIKE 'reply:%'"))
по = {}
for р in ряды:
    if р["domain"] in ПУБЛ:
        continue
    по.setdefault(р["domain"], []).append(р)
много = sorted(((д, с) for д, с in по.items() if len(с) > 1),
               key=lambda x: -len(x[1]))
print("=== СВОДКА ===")
print("  писем рассылки ушло: %d" % len(ряды))
print("  ответов от нас (reply) сверх этого: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND idempotency_key LIKE 'reply:%'").fetchone()[0])
print("  компаний, где письмо получили 2+ человека: %d" % len(много))
print("  писем в этих компаниях: %d" % sum(len(с) for с in dict(много).values()))
print("\n=== ТОП ===")
for д, с in много[:8]:
    им = next((str(x["company_name"]) for x in с if x["company_name"]), д)
    print("  %-2d  %-24s %s" % (len(с), д[:24], им[:30]))
print("\n  осталось не отправлено: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND status='scheduled'").fetchone()[0])
