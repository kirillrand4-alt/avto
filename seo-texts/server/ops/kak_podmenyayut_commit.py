# -*- coding: utf-8 -*-
"""Как pochty_iz_kesha_zapis подменяет commit и что за объект db."""
import io
import re

П = r"C:\sender\server\pochty_iz_kesha_zapis.py"
т = io.open(П, encoding="utf-8", errors="replace").read()
print("=== подмена commit в pochty_iz_kesha_zapis ===")
for м in re.finditer(r"^.{0,110}commit.{0,110}$", т, re.M):
    с = м.group(0).strip()
    if с and not с.lstrip().startswith("#"):
        print("   %5d| %s" % (т[:м.start()].count("\n") + 1, с[:150]))

print("")
print("=== add_email / upsert_company в enrich_db: где commit ===")
E = io.open(r"C:\sender\server\enrich_db.py", encoding="utf-8",
            errors="replace").read()
for имя in ("def add_email", "def upsert_company", "class EnrichDB"):
    i = E.find(имя)
    if i < 0:
        continue
    кусок = E[i:i + 1200]
    print("")
    print("--- %s ---" % имя)
    for j, с in enumerate(кусок.splitlines()[:34]):
        if "commit" in с or "def " in с or "self.cx" in с:
            print("   %s" % с[:140])
