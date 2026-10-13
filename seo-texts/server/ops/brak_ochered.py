# -*- coding: utf-8 -*-
"""Письма, которые не приняла очередь (брак «очередь: …») за сегодня — причины."""
import io
import json
from collections import Counter
св = Counter()
пр = []
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    if "очередь" not in с:
        continue
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    б = " ".join(str(x) for x in (z.get("брак") or []))
    if z.get("день") == "2026-10-13" and б.startswith("очередь"):
        св[б[:60]] += 1
        if len(пр) < 6:
            пр.append("%s | %s | %s" % (z.get("имя"), б[:80], z.get("статус_очереди")))
print(dict(св))
for п in пр:
    print("   " + п)
print("=== БРАК ОЧЕРЕДИ ===")
