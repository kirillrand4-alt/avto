# -*- coding: utf-8 -*-
"""Сработал ли заслон по цене, и чем бракуются письма прогона 9000."""
import io
import json
from collections import Counter
т = io.open(r"C:\sender\_ops\gen-rossiya-9000.log", encoding="utf-8",
            errors="replace").read().rsplit("==== ЗАПУСК", 1)[-1]
for с in т.splitlines():
    if "СТОП ПО ЦЕНЕ" in с or "ОСТАНОВЛЕН" in с.upper() or "дороже" in с:
        print("   " + с.strip()[:200])
ок = т.count("] ОК ")
брак = т.count("] брак")
print("в логе: ок %d, брак %d" % (ок, брак))
прич = Counter()
видели = set()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if z.get("тело") or z.get("цена_$") is None:
        continue
    ключ = z.get("recipient_id")
    if ключ in видели:
        continue
    видели.add(ключ)
    for п in (z.get("брак") or [])[:2]:
        прич[str(п).split(":")[0][:60]] += 1
print("причины брака:")
for п, n in прич.most_common(8):
    print("   %3d  %s" % (n, п))
print("=== ЗАСЛОН 9000 ===")
