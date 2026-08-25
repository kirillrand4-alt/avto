# -*- coding: utf-8 -*-
"""Свод по каталогу ProdExpo: сколько компаний и чего им не хватает."""
import io
import json
import os

ЖУРНАЛ = r"C:\sender\_ops\belarus\katalog-razbor.jsonl"
print("журнал: %s (%d б)" % (ЖУРНАЛ, os.path.getsize(ЖУРНАЛ)
                             if os.path.exists(ЖУРНАЛ) else -1))
компании = {}
страниц = 0
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        d = json.loads(с)
    except Exception:
        continue
    страниц += 1
    for к in (d.get("компании") or []):
        имя = str(к.get("название") or "").strip()
        if имя:
            компании.setdefault(имя.lower(), к)
print("страниц в журнале: %d, компаний: %d" % (страниц, len(компании)))

нет = {"почта": [], "сайт": [], "занятие": [], "телефон": []}
for имя, к in компании.items():
    for поле in нет:
        if not str(к.get(поле) or "").strip():
            нет[поле].append(к.get("название"))
for поле, спис in нет.items():
    print("без «%s»: %d" % (поле, len(спис)))
print("")
print("без сайта: %s" % "; ".join(str(x) for x in нет["сайт"])[:900])
print("")
print("без почты: %s" % "; ".join(str(x) for x in нет["почта"])[:400])
print("")
print("=== три образца ===")
for имя, к in list(компании.items())[:3]:
    print(json.dumps(к, ensure_ascii=False)[:400])
