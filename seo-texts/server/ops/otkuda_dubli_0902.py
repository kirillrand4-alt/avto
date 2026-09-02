# -*- coding: utf-8 -*-
"""Только чтение: кто создал вторые письма в кампании 12."""
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
дубли = [14481, 14482, 14483, 14484, 14485, 14486, 14487]
впис = ",".join("?" * len(дубли))

print("=== КАРТОЧКИ ВТОРЫХ ПИСЕМ ===")
for р in c.execute("SELECT * FROM messages WHERE id IN (%s)" % впис, дубли):
    print("  msg#%s ключ=%s..." % (р["id"], str(р["idempotency_key"])[:28]))
    print("      создано %s, шаг %s, ящик %s, тема %s"
          % (р["created_at"][:19], р["sequence_step_id"], р["mailbox_id"],
             str(р["subject"])[:40]))

об = c.execute("SELECT idempotency_key FROM messages WHERE campaign_id=12"
               " AND id<14400 LIMIT 1").fetchone()
print("\n  для сравнения ключ моего письма: %s..." % str(об["idempotency_key"])[:28])

print("\n=== РЕШЕНИЯ, ПРИВЯЗАННЫЕ К ЭТИМ ПИСЬМАМ ===")
for р in c.execute("SELECT id, message_id, status, kind, reason, created_at, decided_by"
                   " FROM confirm_reviews WHERE message_id IN (%s)" % впис, дубли):
    print("  ревью#%s -> msg#%s статус=%s вид=%s кем=%s создано %s"
          % (р["id"], р["message_id"], р["status"], р["kind"], р["decided_by"],
             str(р["created_at"])[:19]))

print("\n=== АУДИТ ЗА СЕГОДНЯ ===")
таб = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'"
                               " AND name LIKE '%audit%'")]
print("  таблицы аудита: %s" % таб)
for т in таб:
    кол = [r["name"] for r in c.execute("PRAGMA table_info(%s)" % т)]
    for р in c.execute("SELECT * FROM %s WHERE created_at>='2026-09-02'"
                       " ORDER BY id DESC LIMIT 14" % т):
        print("  " + " | ".join("%s=%s" % (k, str(р[k])[:38]) for k in кол
                                if str(р[k]) not in ("None", ""))[:150])

print("\n=== ЕЩЁ НЕ ОТПРАВЛЕННЫЕ В КАМПАНИИ 12 ===")
for р in c.execute("SELECT m.id, r.email, m.status FROM messages m"
                   " JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.campaign_id=12 AND m.status<>'sent'"):
    print("  msg#%s %-34s %s" % (р["id"], р["email"][:34], р["status"]))
