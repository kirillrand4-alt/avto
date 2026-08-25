# -*- coding: utf-8 -*-
"""Письма, снятые МОИМИ прогонами: что именно и сколько."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("=== ПИСЬМА В 'skipped' ПО ПРИЧИНЕ (за вчера-сегодня) ===")
for р in c.execute(
        "SELECT substr(COALESCE(last_error,'(пусто)'),1,52) п, COUNT(*) n "
        "  FROM messages WHERE status='skipped' "
        "   AND updated_at >= datetime('now','-2 days') "
        " GROUP BY п ORDER BY n DESC LIMIT 14"):
    print("  %-54s %5d" % (р["п"], р["n"]))

print("\n=== КАРТОЧКИ approved, ЧЬЁ ПИСЬМО СНЯТО МНОЙ ===")
for р in c.execute(
        "SELECT substr(COALESCE(m.last_error,''),1,46) п, COUNT(*) n "
        "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='approved' AND m.status='skipped' "
        "   AND (m.last_error LIKE '%линза%' OR m.last_error LIKE '%чистка%' "
        "        OR m.last_error LIKE '%дешёв%') "
        " GROUP BY п ORDER BY n DESC"):
    print("  %-48s %5d" % (р["п"], р["n"]))

всего = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status='approved' AND m.status='skipped' "
    "   AND (m.last_error LIKE '%линза%' OR m.last_error LIKE '%чистка%' "
    "        OR m.last_error LIKE '%дешёв%')").fetchone()["n"]
print("  ---- ИТОГО восстановимо: %d" % всего)

print("\n=== И ОТДЕЛЬНО: КАРТОЧКИ, КОТОРЫЕ Я ВЕРНУЛ В pending ===")
н = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews "
    " WHERE status='pending' AND reason LIKE '%устаревшему правилу 2%'"
    ).fetchone()["n"]
print("  их %d — вчера они были подтверждены, я сбросил в ожидание" % н)

print("\n=== ПОЧЕМУ НЕ ИДЁТ ОТПРАВКА (117 scheduled, ушло 1) ===")
for р in c.execute(
        "SELECT m.mailbox_id, COUNT(*) n FROM messages m "
        " WHERE m.status='scheduled' GROUP BY m.mailbox_id ORDER BY n DESC LIMIT 6"):
    print("  ящик %-36s %d писем в scheduled" % (str(р["mailbox_id"])[:36], р["n"]))
for р in c.execute(
        "SELECT scheduled_at, COUNT(*) n FROM messages WHERE status='scheduled' "
        " GROUP BY substr(COALESCE(scheduled_at,''),1,13) ORDER BY 1 DESC LIMIT 6"):
    print("  на %s: %d" % (str(р["scheduled_at"])[:16], р["n"]))
