# -*- coding: utf-8 -*-
"""Кто ждёт подтверждения и что с этим можно сделать."""
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

print("=== PENDING (настоящее ожидание) ===")
for р in c.execute(
        "SELECT cr.id, cr.created_at, cr.subject, cr.reason, r.email, "
        "       r.company_name, COALESCE(m.status,'нет письма') mst, "
        "       COALESCE(p.verdict,'вердикта нет') в "
        "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
        " WHERE cr.status='pending' ORDER BY cr.id"):
    print("\n  #%-6s %s | %s" % (р["id"], str(р["created_at"])[:16],
                                 str(р["company_name"] or "")[:40]))
    print("     адрес %s | проба: %s | письмо: %s"
          % (str(р["email"])[:34], р["в"], р["mst"]))
    print("     тема: %s" % str(р["subject"])[:70])
    if р["reason"]:
        print("     пометка: %s" % str(р["reason"])[:90])

print("\n=== EDITED (виджет считает их ждущими) ===")
for р in c.execute(
        "SELECT COALESCE(m.status,'нет письма') mst, COUNT(*) n, "
        "       MIN(cr.created_at) a, MAX(cr.created_at) b "
        "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.status='edited' GROUP BY mst ORDER BY n DESC"):
    print("  письмо %-16s %4d  (созданы %s .. %s)"
          % (р["mst"], р["n"], str(р["a"])[:10], str(р["b"])[:10]))

print("\n=== ЧТО ЖДЁТ ОТПРАВКИ ===")
for р in c.execute(
        "SELECT m.status, COUNT(*) n FROM messages m "
        " WHERE m.status NOT IN ('sent','skipped','failed') GROUP BY m.status"):
    print("  письмо %-16s %d" % (р["status"], р["n"]))

print("\n=== ПРОСРОЧЕННЫЕ (слот в прошлом) ===")
for р in c.execute(
        "SELECT COUNT(*) n, MIN(scheduled_at) a FROM messages "
        " WHERE status='scheduled' AND scheduled_at < datetime('now')"):
    print("  писем: %d, самое старое на %s" % (р["n"], str(р["a"] or "-")[:16]))

print("\n=== ОТПРАВЛЕНО СЕГОДНЯ ===")
for р in c.execute(
        "SELECT COUNT(*) n FROM messages WHERE status='sent' "
        "  AND substr(COALESCE(sent_at,''),1,10)=date('now')"):
    print("  %d писем" % р["n"])
