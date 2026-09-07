# -*- coding: utf-8 -*-
"""Итог заливки агро: сколько получателей, фактов, и что за упрямые 70."""
import sqlite3, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ИСТОЧНИК = "чеко-агро-2026"
ГРУППА = "Агро зерно 2026"
store = Store(r"C:\sender\sender.db")
поч_инн = {}
свои = set()
with store._lock:
    for и, поч, ист in store._conn.execute(
            "SELECT inn, email, source FROM recipients"):
        поч_инн[str(поч or "").lower()] = str(и or "")
        if str(ист or "") == ИСТОЧНИК:
            свои.add(str(и or ""))
группы = store.recipient_groups().get("по_id") or {}
в_группе = sum(1 for g in группы.values() if ГРУППА in (g or []))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=120)
агро = {str(r[0]) for r in e.execute(
    "SELECT inn FROM requisites WHERE src='checko-sbor-agro'")}
в_обог = {str(r[0]) for r in e.execute("SELECT inn FROM companies")}
e.close()

print("=" * 70)
print("=== ИТОГ ЗАЛИВКИ ===")
print("получателей с источником %s: %d" % (ИСТОЧНИК, len(свои)))
print("в группе «%s»: %d" % (ГРУППА, в_группе))
print("агро-ИНН всего в requisites: %d; из них в enrich.companies: %d"
      % (len(агро), len(агро & в_обог)))
print("наших ИНН без строки в обогащении: %d" % len(свои - в_обог))
