# -*- coding: utf-8 -*-
"""Сколько писем ушло и лежит в очереди с неподставленным ИМЯ_ОТПРАВИТЕЛЯ."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

for имя, запрос in (
    ("ОТПРАВЛЕННЫЕ (messages.body_rendered)",
     "SELECT COUNT(*) FROM messages WHERE sent_at IS NOT NULL "
     "  AND body_rendered LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%'"),
    ("отправленных всего",
     "SELECT COUNT(*) FROM messages WHERE sent_at IS NOT NULL"),
    ("В ОЧЕРЕДИ (confirm_reviews)",
     "SELECT COUNT(*) FROM confirm_reviews WHERE status IN "
     "('pending','approved','edited') AND (COALESCE(edited_body,body) "
     "LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%')"),
    ("в очереди всего",
     "SELECT COUNT(*) FROM confirm_reviews WHERE status IN "
     "('pending','approved','edited')"),
    ("УЖЕ ОТПРАВЛЕННЫЕ карточки с дырой",
     "SELECT COUNT(*) FROM confirm_reviews WHERE status='sent' "
     "  AND (COALESCE(edited_body,body) LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%')"),
):
    print("%-42s %d" % (имя, c.execute(запрос).fetchone()[0]))

print("")
print("=== по ящикам: сколько ушло с дырой ===")
for r in c.execute(
        "SELECT m.mailbox_id, COUNT(*) n FROM messages m "
        " WHERE m.sent_at IS NOT NULL AND m.body_rendered LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%' "
        " GROUP BY m.mailbox_id ORDER BY n DESC"):
    print("   %-42s %d" % (str(r["mailbox_id"])[:42], r["n"]))

print("")
print("=== по дням ===")
for r in c.execute(
        "SELECT substr(sent_at,1,10) д, COUNT(*) n FROM messages "
        " WHERE sent_at IS NOT NULL AND body_rendered LIKE '%ИМЯ_ОТПРАВИТЕЛЯ%' "
        " GROUP BY д ORDER BY д"):
    print("   %s  %d" % (r["д"], r["n"]))

print("")
print("=== другие незакрытые метки ===")
for метка in ("ИМЯ_ОТПРАВИТЕЛЯ", "{{", "}}", "ИМЯ_КОМПАНИИ", "ГОРОД",
              "НАЗВАНИЕ_КОМПАНИИ", "ДОЛЖНОСТЬ"):
    n = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE status IN "
                  "('pending','approved','edited') AND COALESCE(edited_body,body) "
                  "LIKE ?", ("%" + метка + "%",)).fetchone()[0]
    if n:
        print("   %-22s в очереди: %d" % (метка, n))
c.close()
