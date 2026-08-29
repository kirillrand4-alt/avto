# -*- coding: utf-8 -*-
"""Писали ли мы АО «ОКБ «Экситон» (ИНН 5035025460) и с какого ящика."""
import sqlite3
БАЗА = r"C:\sender\sender.db"
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("получатели с этим ИНН:")
for r in c.execute("SELECT id, email, company_name, segment FROM recipients "
                   " WHERE inn='5035025460'"):
    print("   rid=%s %s %s (%s)" % (r["id"], r["email"], r["company_name"],
                                    r["segment"]))
print("\nжурнал отправок по ИНН и по домену:")
for r in c.execute("SELECT ts, email, subject, outcome FROM send_log "
                   " WHERE inn='5035025460' OR email LIKE '%okbexiton%' "
                   " ORDER BY ts"):
    print("   %s %-30s %-40s %s" % (str(r["ts"])[:19], r["email"],
                                    str(r["subject"])[:40], r["outcome"]))
print("\nчерновики:")
for r in c.execute("SELECT id, email, status, kind, "
                   "       COALESCE(decided_at,updated_at) ts, "
                   "       COALESCE(edited_subject,subject) tema "
                   "  FROM confirm_reviews WHERE inn='5035025460' "
                   "     OR email LIKE '%okbexiton%'"):
    print("   review=%s %s %s %s %s :: %s" % (r["id"], str(r["ts"])[:19],
                                              r["email"], r["status"],
                                              r["kind"], str(r["tema"])[:40]))
print("\nв стоп-листе:")
for r in c.execute("SELECT scope, value, reason FROM suppression "
                   " WHERE value LIKE '%okbexiton%' OR value='5035025460'"):
    print("   %s %s — %s" % (r["scope"], r["value"], r["reason"]))
print("\nв лидах:")
for r in c.execute("SELECT id, email, company_name, status FROM leads "
                   " WHERE email LIKE '%okbexiton%' OR inn='5035025460'"):
    print("   лид=%s %s %s %s" % (r["id"], r["email"], r["company_name"],
                                  r["status"]))
c.close()
