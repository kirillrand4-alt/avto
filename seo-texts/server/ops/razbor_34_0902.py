# -*- coding: utf-8 -*-
"""Только чтение: из-за чего снят каждый из «уже писали» — адрес или компания."""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

ряды = list(c.execute(
    "SELECT m.id, r.email, r.inn, r.company_name, m.last_error FROM messages m"
    " JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=12 AND m.status='skipped'"
    " AND m.last_error LIKE 'auto_send:уже писали%'"))
print("снято как «уже писали»: %d" % len(ряды))

по_адресу, по_компании = [], []
for р in ряды:
    почта = (р["email"] or "").lower()
    инн = "".join(x for x in str(р["inn"] or "") if x.isdigit())
    ф = store.sent_flags(emails=[почта], inns=[инн] if инн else None) or {}
    адрес_был = bool((ф.get(почта) or {}).get("ever"))
    (по_адресу if адрес_был else по_компании).append(р)

print("\n=== ПИСАЛИ НА ЭТОТ ЖЕ АДРЕС: %d (проталкивать не стоит) ===" % len(по_адресу))
for р in по_адресу:
    print("  %-34s %-24s %s" % (р["email"][:34], str(р["company_name"])[:24],
                                str(р["last_error"])[-12:]))

print("\n=== ПИСАЛИ ТОЛЬКО В КОМПАНИЮ, АДРЕС НОВЫЙ: %d (можно толкать) ==="
      % len(по_компании))
for р in по_компании:
    print("  %-34s %-24s %s" % (р["email"][:34], str(р["company_name"])[:24],
                                str(р["last_error"])[-12:]))
