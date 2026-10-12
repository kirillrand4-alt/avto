# -*- coding: utf-8 -*-
"""Кого линза отправила «переставить на КЦ» — по отраслям и станку письма."""
import io
import re
import sqlite3
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AL  # noqa: E402

т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8",
            errors="replace").read().rsplit("==== ЗАПУСК", 1)[-1]
имена = []
for с in т.splitlines():
    if "] брак" in с and "переставить на kc" in с:
        м = re.search(r"meyer\s+(.+?)\s{2,}\d+с", с)
        if м:
            имена.append(м.group(1).strip())
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
по = Counter()
pains = AL._okved_pains()
for имя in имена:
    р = c.execute("SELECT segment, okved FROM recipients WHERE company_name=? "
                  "AND extra_json LIKE '%Россия 9000%' LIMIT 1", (имя,)).fetchone()
    if not р:
        по[("?", "?")] += 1
        continue
    станок = AL._градация_мейера(str(р[1] or ""), pains)
    по[(р[0] or "?", станок)] += 1
print("переставить на КЦ: %d писем" % len(имена))
for (отр, ст), n in по.most_common():
    print("   %-32s станок письма %-14s %3d" % (отр[:32], ст, n))
print("=== ПЕРЕСТАВИТЬ ===")
