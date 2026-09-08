# -*- coding: utf-8 -*-
"""Карточка лида АГРО-ХОРС целиком: текст автоответа и адреса в нём."""
import re, sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ИНН = sys.argv[1] if len(sys.argv) > 1 else "6316219819"
АДРЕС = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
ТЕЛЕФОН = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")
store = Store(r"C:\sender\sender.db")
with store._lock:
    кол = [c[1] for c in store._conn.execute("PRAGMA table_info(leads)")]
    р = store._conn.execute("SELECT * FROM leads WHERE inn=?", (ИНН,)).fetchone()
if р is None:
    print("лида с таким ИНН нет")
    raise SystemExit(1)
текст = ""
for k in кол:
    з = р[k]
    if k == "need" and isinstance(з, str):
        текст = з
        continue
    if з not in (None, ""):
        print("   %-18s %s" % (k, str(з)[:100]))
print("")
print("--- текст автоответа целиком ---")
print(текст)
print("")
print("=" * 74)
print("=== ЧТО ЕСТЬ В АВТООТВЕТЕ ===")
наши = ("optic-sort", "zernosort", "sort-systems", "food-sort",
        "sorting-systems", "rentgen", "optical-sort", "inspection-systems")
адреса = [a for a in sorted(set(АДРЕС.findall(текст)))
          if not any(d in a for d in наши)]
print("адреса: %s" % (", ".join(адреса) or "нет"))
print("телефоны: %s" % (", ".join(sorted(set(ТЕЛЕФОН.findall(текст)))) or "нет"))
