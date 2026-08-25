# -*- coding: utf-8 -*-
"""Что вообще лежит в журналах и в карточках — колонки и ключи, без догадок."""
import io
import json
import os
import sqlite3

c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
for т in ("confirm_reviews", "messages"):
    кол = [р[1] for р in c.execute("PRAGMA table_info(%s)" % т)]
    print("%s: %s" % (т, ", ".join(кол)))

print("\nдиапазон дат карточек:")
for р in c.execute("SELECT substr(created_at,1,10) д, COUNT(*) n "
                   "  FROM confirm_reviews GROUP BY д ORDER BY д DESC LIMIT 8"):
    print("   %s  %5d" % (р[0], р[1]))

КАТАЛОГ = r"C:\sender\_ops"
for имя in ("gen-partiya-935.jsonl", "deshevaya-partiya.jsonl",
            "tysyacha-sonnet.jsonl"):
    п = os.path.join(КАТАЛОГ, имя)
    if not os.path.exists(п):
        print("\n%s — нет файла" % имя)
        continue
    строки = io.open(п, encoding="utf-8", errors="replace").readlines()
    print("\n%s: строк %d" % (имя, len(строки)))
    for с in строки[-2:]:
        try:
            з = json.loads(с)
        except Exception:  # noqa: BLE001
            print("   не json: %s" % с[:80])
            continue
        print("   ключи: %s" % ", ".join(sorted(з)))
        print("   ts=%r время=%r дата=%r" % (з.get("ts"), з.get("время"),
                                             з.get("дата")))
