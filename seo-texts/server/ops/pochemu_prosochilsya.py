# -*- coding: utf-8 -*-
"""Почему zakupki@stmost.ru прошёл отбор, хотя был в стоп-листе неделю."""
import sqlite3
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("=== запись в стоп-листе ===")
for r in c.execute("SELECT id, scope, value, reason, created_at, expires_at "
                   "  FROM suppression WHERE value LIKE '%stmost%'"):
    print("   %s" % dict(r))
print("\n=== получатель ===")
for r in c.execute("SELECT id, email, domain, inn, company_name FROM recipients "
                   " WHERE email LIKE '%stmost%'"):
    print("   %s" % dict(r))
print("\n=== сходится ли JOIN отбора ===")
for r in c.execute(
        "SELECT r.id, r.email, s.id AS sid, s.scope, s.value "
        "  FROM recipients r LEFT JOIN suppression s ON "
        "    (s.expires_at IS NULL OR s.reason='unsubscribe') AND ("
        "    (s.scope='email' AND s.value=lower(trim(r.email))) OR "
        "    (s.scope='domain' AND s.value=lower(trim(r.domain))) OR "
        "    (s.scope='inn' AND r.inn IS NOT NULL "
        "     AND s.value=replace(replace(trim(r.inn),' ',''),'-',''))) "
        " WHERE r.email LIKE '%stmost%'"):
    print("   rid=%s %s → запись стоп-листа %s (%s %s)"
          % (r["id"], r["email"], r["sid"], r["scope"], r["value"]))
print("\n=== черновик ===")
for r in c.execute("SELECT id, email, status, created_at, campaign_id, "
                   "       recipient_id FROM confirm_reviews WHERE id=1073"):
    print("   %s" % dict(r))
print("\n=== сколько ещё записей стоп-листа не сойдутся с получателем ===")
n = c.execute(
    "SELECT COUNT(*) FROM suppression s WHERE s.scope='email' "
    "  AND s.value <> LOWER(TRIM(s.value))").fetchone()[0]
print("   значений не в нижнем регистре/с пробелами: %d" % n)
m = c.execute("SELECT COUNT(*) FROM suppression WHERE scope NOT IN "
              "  ('email','domain','inn')").fetchone()[0]
print("   записей с непонятным scope: %d" % m)
c.close()
