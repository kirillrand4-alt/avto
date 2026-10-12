# -*- coding: utf-8 -*-
"""Полные претензии «НЕ ПОКУПАТЕЛЬ» по именам (журнал 9000): ne_pokupatel_polnostyu.py <regex имени>."""
import io
import json
import re
import sys
рег = re.compile(sys.argv[1], re.I)
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8",
                 errors="replace").read().splitlines()[-300:]:
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if not рег.search(str(z.get("имя"))) or not z.get("брак"):
        continue
    print("## %s | %s | %s" % (z.get("имя"), z.get("день"), str(z.get("напр_почему"))[:200]))
    print("   " + json.dumps(z.get("брак"), ensure_ascii=False)[:900])
print("=== ГОТОВО ===")
