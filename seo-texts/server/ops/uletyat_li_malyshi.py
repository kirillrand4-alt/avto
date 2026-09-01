# -*- coding: utf-8 -*-
"""Может ли ещё улететь письмо компании ниже порога."""
import sqlite3
from collections import Counter

ПОРОГ = 30_000_000
ЛЕТУЧИЕ = ("scheduled", "pending_review", "sending", "queued")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
мелкие = {цифры(r[0]) for r in e.execute(
    "SELECT inn FROM companies WHERE revenue_rub IS NOT NULL"
    "   AND revenue_rub > 0 AND revenue_rub < ?", (ПОРОГ,))}
e.close()

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
c.row_factory = sqlite3.Row
св = Counter()
летучих = []
for r in c.execute(
        "SELECT m.id, m.status, m.sent_at, r.inn, r.company_name"
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id"
        " WHERE m.campaign_id=11 AND r.inn IS NOT NULL"):
    if цифры(r["inn"]) not in мелкие:
        continue
    if r["sent_at"]:
        св["уже отправлено (не вернуть)"] += 1
    elif str(r["status"]) in ЛЕТУЧИЕ:
        св["ЕЩЁ МОЖЕТ УЛЕТЕТЬ"] += 1
        летучих.append((r["id"], r["status"], r["company_name"]))
    else:
        св["снято (%s)" % r["status"]] += 1
c.close()

print("=== ПИСЬМА КОМПАНИЯМ НИЖЕ 30 МЛН, КАМПАНИЯ 11 ===")
for к, n in св.most_common():
    print("   %-30s %5d" % (к, n))
print("\n   из тех, что ещё могут улететь:")
for i, с, имя in летучих[:10]:
    print("      письмо %s (%s) — %s" % (i, с, str(имя)[:40]))
print("\n=== ИТОГ ===")
print("осталось летучих: %d" % len(летучих))
