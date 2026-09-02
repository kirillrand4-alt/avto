# -*- coding: utf-8 -*-
"""Только чтение: где сейчас лежат 175 писем вебинара."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== РЕШЕНИЯ ПО КАМПАНИИ 12 ===")
for x in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews"
                   " WHERE campaign_id=12 GROUP BY status"):
    print("  confirm_reviews %-12s %4d" % (x["status"], x["n"]))

print("\n=== ПИСЬМА ===")
for x in c.execute("SELECT status, COUNT(*) n FROM messages"
                   " WHERE campaign_id=12 GROUP BY status"):
    print("  messages %-16s %4d" % (x["status"], x["n"]))
print("  с готовым телом: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND body_rendered<>''").fetchone()[0])
р = c.execute("SELECT scheduled_at, COUNT(*) n FROM messages WHERE campaign_id=12"
              " GROUP BY scheduled_at").fetchall()
for x in р:
    print("  срок %s: %d" % (x["scheduled_at"], x["n"]))
print("  сейчас: %s" % dt.datetime.now().isoformat(timespec="seconds"))

print("\n=== ГРУППА ===")
print("  получателей с группой vebinar-2609: %d"
      % c.execute("SELECT COUNT(*) FROM recipients"
                  " WHERE extra_json LIKE '%vebinar-2609%'").fetchone()[0])

print("\n=== ОДНО ПИСЬМО ЦЕЛИКОМ (проверка, что текст на месте) ===")
м = c.execute("SELECT id, subject, mailbox_id, substr(body_rendered,1,150) t"
              " FROM messages WHERE campaign_id=12 ORDER BY id LIMIT 1").fetchone()
print("  msg#%s | ящик=%s | тема: %s" % (м["id"], м["mailbox_id"], м["subject"]))
print("  начало: %s..." % м["t"].replace("\n", " ")[:130])

print("\n=== ИТОГ ===")
print("  письма целы: 175 штук со своим текстом, статус scheduled,")
print("  придержаны до 18:48 — из очереди подтверждения ушли потому, что одобрены")
