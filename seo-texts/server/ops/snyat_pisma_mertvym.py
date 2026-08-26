# -*- coding: utf-8 -*-
"""Снять из очереди письма на адреса с приговором «мёртв».

44 таких письма ждали подтверждения: приговор был, а письмо всё равно
стояло в очереди — потому что вердикт не доехал до стоп-листа, а заслон
подтверждения читает именно его.

    python snyat_pisma_mertvym.py            # показать
    python snyat_pisma_mertvym.py primenit   # снять
"""
import sqlite3
import sys
import time

ДЕЛАТЬ = "primenit" in sys.argv[1:]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, cr.status, cr.message_id, r.email, p.verdict, "
    "       substr(cr.subject,1,46) s "
    "  FROM confirm_reviews cr "
    "  JOIN recipients r ON r.id=cr.recipient_id "
    "  JOIN addr_probe p ON p.email=r.email "
    " WHERE p.verdict IN ('нет ящика','нет MX') "
    "   AND cr.status IN ('pending','approved','edited') ORDER BY cr.id"
).fetchall()
print("писем на мёртвые адреса в очереди: %d" % len(ряды))
for r in ряды[:10]:
    print("   #%-6s %-9s %-34s %-10s %s"
          % (r["id"], r["status"], r["email"][:34], r["verdict"], r["s"]))
if not ДЕЛАТЬ:
    print("\nвхолостую. Снять — primenit")
    raise SystemExit(0)

сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
снято = 0
for r in ряды:
    причина = "адрес недоставим: %s (проба)" % r["verdict"]
    c.execute("UPDATE confirm_reviews SET status='skipped', reason=?, "
              "decided_at=?, decided_by='проба адресов', updated_at=? "
              " WHERE id=? AND status IN ('pending','approved','edited')",
              (причина, сейчас, сейчас, r["id"]))
    if r["message_id"]:
        c.execute("UPDATE messages SET status='skipped', last_error=?, "
                  "updated_at=? WHERE id=? AND status NOT IN ('sent','sending')",
                  (причина, сейчас, r["message_id"]))
    снято += 1
c.commit()
c.close()
print("\nснято писем: %d" % снято)
