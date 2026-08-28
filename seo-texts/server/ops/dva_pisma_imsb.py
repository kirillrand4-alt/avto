# -*- coding: utf-8 -*-
import io, json, sqlite3
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== получатели на imsb.ru ===")
for r in c.execute("SELECT id, email, inn, company_name, source FROM recipients "
                   " WHERE domain='imsb.ru' OR email LIKE '%@imsb.ru'"):
    print("   rid %-6s %-26s ИНН %-13s источник %s"
          % (r["id"], r["email"], r["inn"], str(r["source"])[:20]))
print("")
print("=== письма ===")
for r in c.execute(
        "SELECT m.id, m.status, m.sent_at, m.mailbox_id, m.campaign_id, rc.email, "
        "       cr.id crid, cr.reason, cr.decided_by "
        "  FROM messages m JOIN recipients rc ON rc.id=m.recipient_id "
        "  LEFT JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE rc.email LIKE '%@imsb.ru' ORDER BY m.sent_at"):
    print("   msg %-6s %-8s %s  %-26s ящик %s"
          % (r["id"], r["status"], str(r["sent_at"])[:16], str(r["email"])[:26],
             str(r["mailbox_id"])[:28]))
    print("      карточка %s | решил: %s | причина: %s"
          % (r["crid"], r["decided_by"], str(r["reason"])[:80]))
print("")
print("=== send_log по компании ===")
for r in c.execute("SELECT ts, email, outcome FROM send_log "
                   " WHERE email LIKE '%@imsb.ru' ORDER BY ts"):
    print("   %s  %-26s %s" % (str(r["ts"])[:19], str(r["email"])[:26], r["outcome"]))
c.close()
партии = {}
for ф, п in ((r"C:\sender\_ops\vtorye-adresa.jsonl", 1),
             (r"C:\sender\_ops\vtorye-adresa-2.jsonl", 2)):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "imsb.ru" in str(d.get("email", "")):
                print("в партии %d: %s (карточка %s)" % (п, d["email"], d["review"]))
    except FileNotFoundError:
        pass
