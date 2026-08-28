# -*- coding: utf-8 -*-
"""Не стоит ли в очереди письмо на адрес, который уже отбился намертво."""
import sqlite3
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
строки = list(c.execute(
    "SELECT m.id, m.status, m.scheduled_at, r.email, r.company_name, "
    "       s.reason, s.value "
    "  FROM messages m "
    "  JOIN recipients r ON r.id = m.recipient_id "
    "  JOIN suppression s ON LOWER(s.value) = LOWER(r.email) "
    " WHERE m.status IN ('scheduled','pending_review','sending') "
    " ORDER BY m.scheduled_at"))
print("писем в очереди на адрес из стоп-листа: %d" % len(строки))
по_причине = {}
for r in строки:
    по_причине[r["reason"]] = по_причине.get(r["reason"], 0) + 1
for к, v in sorted(по_причине.items(), key=lambda x: -x[1]):
    print("   %-24s %d" % (к, v))
print()
жёстких = [r for r in строки if str(r["reason"] or "") in
           ("bounce_hard", "hard_bounce", "нет MX (подтверждено дважды)")]
print("из них по мёртвому ящику/домену: %d" % len(жёстких))
for r in жёстких[:25]:
    print("   msg=%-7s %-9s %s  %-34s %s"
          % (r["id"], r["status"], str(r["scheduled_at"])[:16], r["email"],
             str(r["company_name"] or "")[:28]))
print()
print("=== то же по адресам с приговором пробы ===")
n = c.execute(
    "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "  JOIN addr_probe p ON LOWER(p.email)=LOWER(r.email) "
    " WHERE m.status IN ('scheduled','pending_review','sending') "
    "   AND p.verdict IN ('нет ящика','нет MX')").fetchone()[0]
print("писем в очереди на адрес с приговором пробы: %d" % n)
for r in c.execute(
        "SELECT m.id, m.status, r.email, p.verdict, r.company_name "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "  JOIN addr_probe p ON LOWER(p.email)=LOWER(r.email) "
        " WHERE m.status IN ('scheduled','pending_review','sending') "
        "   AND p.verdict IN ('нет ящика','нет MX') LIMIT 25"):
    print("   msg=%-7s %-9s %-12s %-34s %s"
          % (r["id"], r["status"], r["verdict"], r["email"],
             str(r["company_name"] or "")[:28]))
c.close()
