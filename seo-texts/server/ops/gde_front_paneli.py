# -*- coding: utf-8 -*-
"""Где лежит фронт панели и какие ключи инфо-панели он рисует.

Нужно, чтобы подпись «кто писал письмо» оказалась там, где оператор её
увидит, а не только в базе.
"""
import io
import os
import re

найдено = []
for корень in (r"C:\sender",):
    for папка, _, файлы in os.walk(корень):
        if "node_modules" in папка or "\\.git" in папка:
            continue
        for ф in файлы:
            if ф.endswith((".js", ".tsx")) and os.path.getsize(
                    os.path.join(папка, ф)) > 20000:
                п = os.path.join(папка, ф)
                try:
                    т = io.open(п, encoding="utf-8", errors="replace").read()
                except Exception:  # noqa: BLE001
                    continue
                if "letter_division" in т:
                    найдено.append((п, т))
print("файлов фронта с letter_division: %d" % len(найдено))
for п, т in найдено[:3]:
    print("")
    print("### %s (%d байт)" % (п, len(т)))
    for м in re.finditer(r".{0,90}letter_division.{0,120}", т):
        print("   …%s…" % м.group(0).replace("\n", " ")[:210])
    for ключ in ("letter_division_reason", "news_digest", "quota_day",
                 "rounds", "model"):
        print("   ключ %-24s встречается %d раз" % (ключ, т.count(ключ)))
print("")
print("=== ФРОНТ ПАНЕЛИ ===")
