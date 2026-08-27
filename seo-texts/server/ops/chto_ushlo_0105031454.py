# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
ИНН = "0105031454"
print("=== все отправленные письма компании ===")
for r in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.subject, m.campaign_id, r.email "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE r.inn=? ORDER BY m.sent_at", (ИНН,)):
    print("   msg %-6s %-8s %s  camp %-3s %-28s %s"
          % (r["id"], r["status"], str(r["sent_at"])[:16], r["campaign_id"],
             r["email"][:28], str(r["subject"])[:44]))
print("=== карточки подтверждения ===")
for r in c.execute(
        "SELECT id, status, message_id, campaign_id, email, subject "
        "  FROM confirm_reviews WHERE inn=? ORDER BY id", (ИНН,)):
    print("   rev %-6s %-10s msg=%-6s camp %-3s %-26s %s"
          % (r["id"], r["status"], r["message_id"], r["campaign_id"],
             str(r["email"])[:26], str(r["subject"])[:42]))
c.close()
