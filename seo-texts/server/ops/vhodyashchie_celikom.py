# -*- coding: utf-8 -*-
"""Тексты входящих, из которых взяты адреса-копии: смотрим имена глазами."""
import sqlite3
import sys

АДРЕСА = [a.lower() for a in sys.argv[1:] if "@" in a]
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for а in АДРЕСА:
    print("=" * 72)
    print(а)
    было = False
    for r in c.execute(
            "SELECT id, company_name, COALESCE(need,'') need FROM leads "
            "WHERE lower(COALESCE(email,''))=? OR lower(COALESCE(need,'')) "
            "LIKE ? ORDER BY id DESC LIMIT 2", (а, f"%{а}%")):
        было = True
        print(f"  лид #{r['id']} {r['company_name']}")
        print("  " + str(r["need"])[:900].replace("\n", "\n  "))
    if not было:
        print("  входящего с этим адресом не нашлось")
