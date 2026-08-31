# -*- coding: utf-8 -*-
"""Из чего складываются 7959 писем «живой очереди»."""
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row

print("=== РАЗБИВКА ПО КАМПАНИЯМ И СТАТУСАМ ===")
всего = 0
for r in c.execute(
        "SELECT cr.campaign_id k, COALESCE(c2.name,'') имя, cr.status st,"
        "       COUNT(*) n FROM confirm_reviews cr"
        "  LEFT JOIN campaigns c2 ON c2.id=cr.campaign_id"
        " WHERE cr.status IN ('pending','approved','edited')"
        "   AND COALESCE(cr.kind,'outbound') <> 'reply'"
        " GROUP BY cr.campaign_id, cr.status ORDER BY n DESC"):
    всего += r["n"]
    print("   %-4s %-24s %-10s %6d" % (r["k"], r["имя"][:24], r["st"], r["n"]))
print("   ИТОГО %d" % всего)

print("\n=== ЧТО С ПИСЬМАМИ ЭТИХ КАРТОЧЕК ===")
for r in c.execute(
        "SELECT cr.status st, COALESCE(m.status,'нет письма') ms,"
        "       COUNT(*) n FROM confirm_reviews cr"
        "  LEFT JOIN messages m ON m.id = cr.message_id"
        " WHERE cr.status IN ('pending','approved','edited')"
        "   AND COALESCE(cr.kind,'outbound') <> 'reply'"
        " GROUP BY cr.status, ms ORDER BY n DESC LIMIT 14"):
    print("   карточка %-10s письмо %-16s %6d" % (r["st"], r["ms"], r["n"]))

print("\n=== ВОЗРАСТ КАРТОЧЕК ЖИВОЙ ОЧЕРЕДИ ===")
for r in c.execute(
        "SELECT substr(cr.created_at,1,7) месяц, cr.status st, COUNT(*) n"
        "  FROM confirm_reviews cr"
        " WHERE cr.status IN ('pending','approved','edited')"
        "   AND COALESCE(cr.kind,'outbound') <> 'reply'"
        " GROUP BY месяц, cr.status ORDER BY месяц DESC, n DESC"):
    print("   %s  %-10s %6d" % (r[0], r[1], r[2]))

print("\n=== APPROVED, КОТОРЫЕ ТАК И НЕ УШЛИ ===")
r = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews cr"
    " LEFT JOIN messages m ON m.id=cr.message_id"
    " WHERE cr.status='approved' AND COALESCE(cr.kind,'outbound') <> 'reply'"
    "   AND (m.sent_at IS NULL)").fetchone()
print("   одобрено, но письмо не отправлено: %d" % r["n"])
r2 = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews cr"
    " JOIN messages m ON m.id=cr.message_id"
    " WHERE cr.status='approved' AND m.sent_at IS NOT NULL").fetchone()
print("   одобрено и отправлено (в очереди висят как approved): %d" % r2["n"])
print("\n   самые старые неотправленные одобренные:")
for r3 in c.execute(
        "SELECT cr.id, cr.campaign_id, substr(cr.created_at,1,16) когда,"
        "       COALESCE(m.status,'нет письма') ms FROM confirm_reviews cr"
        "  LEFT JOIN messages m ON m.id=cr.message_id"
        " WHERE cr.status='approved' AND m.sent_at IS NULL"
        " ORDER BY cr.created_at LIMIT 6"):
    print("      %6s кампания %-3s %s  письмо: %s"
          % (r3[0], r3[1], r3[2], r3[3]))
c.close()
print("\n=== ИТОГ ===")
print("«живая очередь» = pending + approved + edited, без ответов.")
print("Основная её масса — НЕ сегодняшние письма, а накопленный запас")
print("одобренных, которые ещё не ушли.")
