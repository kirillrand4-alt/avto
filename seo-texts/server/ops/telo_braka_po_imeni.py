# -*- coding: utf-8 -*-
"""Последний текст брака по имени (журнал 9000): telo_braka_po_imeni.py <regex>."""
import io
import json
import re
import sys
рег = re.compile(sys.argv[1], re.I)
посл = {}
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if рег.search(str(z.get("имя"))) and z.get("тело_брака"):
        посл[z.get("имя")] = z
for имя, z in посл.items():
    print("## %s | %s" % (имя, json.dumps(z.get("брак"), ensure_ascii=False)[:200]))
    print(str(z.get("тело_брака"))[:1500])
print("=== ГОТОВО ===")
