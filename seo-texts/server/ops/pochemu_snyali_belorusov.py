# -*- coding: utf-8 -*-
"""Почему сняли 44 письма белорусским компаниям."""
import sqlite3
from collections import Counter

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row
ключи = {str(r["inn"]) for r in s.execute(
    "SELECT inn FROM recipients WHERE inn LIKE '9990%' "
    "   OR COALESCE(extra_json,'') LIKE '%prodexpo%'")}
ряды = [dict(r) for r in s.execute(
    "SELECT cr.*, r.email, r.company_name FROM confirm_reviews cr "
    "  LEFT JOIN recipients r ON r.id = cr.recipient_id "
    " WHERE cr.inn IN (%s)" % ",".join("?" * len(ключи)), tuple(ключи))]
s.close()

причины = Counter()
кто = Counter()
примеры = {}
for р in ряды:
    if str(р.get("status")) != "skipped":
        continue
    п = str(р.get("reason") or "(без причины)")[:80]
    причины[п] += 1
    кто[str(р.get("decided_by") or "?")] += 1
    примеры.setdefault(п, []).append(
        "%s | %s" % (str(р.get("company_name"))[:32], str(р.get("email"))[:30]))

print("=" * 80)
print("=== СВОДКА: ПОЧЕМУ СНЯЛИ ПИСЬМА БЕЛОРУСАМ ===")
print("карточек всего: %d, снятых: %d"
      % (len(ряды), sum(причины.values())))
print("")
print("--- ПРИЧИНЫ ---")
for к, в in причины.most_common():
    print("   %4d  %s" % (в, к))
print("")
print("--- КТО РЕШИЛ ---")
for к, в in кто.most_common():
    print("   %-28s %4d" % (к, в))
print("")
print("--- ПРИМЕРЫ ПО КАЖДОЙ ПРИЧИНЕ ---")
for п, спис in list(примеры.items())[:6]:
    print("   %s:" % п[:70])
    for с in спис[:3]:
        print("      " + с)
