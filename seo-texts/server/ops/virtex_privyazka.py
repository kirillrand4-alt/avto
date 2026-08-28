# -*- coding: utf-8 -*-
import io, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== получатели на virtex-food.ru ===")
for r in c.execute("SELECT id, email, inn, company_name FROM recipients "
                   " WHERE email LIKE '%virtex-food.ru' OR domain='virtex-food.ru'"):
    print("   rid %-6s %-30s ИНН %-13s %s"
          % (r["id"], r["email"], r["inn"], str(r["company_name"] or "")[:34]))
print("")
print("=== письма им ===")
for r in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.rfc_message_id, rc.email "
        "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
        " WHERE rc.domain='virtex-food.ru' OR rc.email LIKE '%virtex-food.ru' "
        " ORDER BY m.id DESC LIMIT 6"):
    print("   msg %-6s %-9s %s  %s" % (r["id"], r["status"],
                                       str(r["sent_at"])[:16], str(r["email"])[:30]))
    print("      rfc: %s" % str(r["rfc_message_id"])[:80])
c.close()
print("")
т = io.open(r"C:\sender\sender\imap_watcher.py", encoding="utf-8").read()
for имя in ("_recipient_by_emails", "_recipient_by_domain", "_recipient_by_imya_domena",
            "luchshee_telo"):
    print("   в серверном imap_watcher: %-28s %s"
          % (имя, "ЕСТЬ" if имя in т else "НЕТ"))
