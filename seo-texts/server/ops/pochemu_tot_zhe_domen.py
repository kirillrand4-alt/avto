# -*- coding: utf-8 -*-
"""Почему после отбивки info@impeks-don.ru письмо ушло на mail@impeks-don.ru."""
import sqlite3
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== стоп-лист по этой компании ===")
for s in c.execute("SELECT * FROM suppression WHERE value LIKE '%impeks-don%' "
                   "   OR value='6167128827'"):
    d = dict(s)
    print("  %s | причина %s | %s" % (d.get("value"), d.get("reason"),
                                      d.get("created_at") or d.get("ts")))
print()
print("=== проба адресов ===")
for p in c.execute("SELECT email, verdict, mx, ts FROM addr_probe "
                   " WHERE email LIKE '%impeks-don.ru'"):
    print("  %-28s %-16s mx=%s  %s" % (p["email"], p["verdict"],
                                       str(p["mx"])[:28], p["ts"]))
print()
print("=== что и когда отправляли ===")
for m in c.execute(
        "SELECT m.id, m.sent_at, m.status, r.email "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE r.inn='6167128827' ORDER BY m.id"):
    print("  msg=%s %s %s -> %s" % (m["id"], str(m["sent_at"])[:19],
                                    m["status"], m["email"]))
print()
print("=== отбивки/события по домену ===")
for e in c.execute(
        "SELECT e.id, e.event_type, e.event_ts, r.email FROM events e "
        "  JOIN recipients r ON r.id=e.recipient_id "
        " WHERE r.inn='6167128827' AND e.event_type IN "
        "       ('bounce','dsn','suppress') ORDER BY e.event_ts"):
    print("  ev=%s %-9s %s  %s" % (e["id"], e["event_type"],
                                   str(e["event_ts"])[:19], e["email"]))
print()
print("=== стоп-лист доменного уровня вообще бывает? ===")
for r_, n in c.execute("SELECT reason, COUNT(*) FROM suppression "
                       " GROUP BY reason ORDER BY 2 DESC LIMIT 12"):
    print("  %-18s %d" % (r_, n))
n = c.execute("SELECT COUNT(*) FROM suppression WHERE value NOT LIKE '%@%'"
              ).fetchone()[0]
print("  записей без «@» (домены/ИНН): %d" % n)
c.close()
