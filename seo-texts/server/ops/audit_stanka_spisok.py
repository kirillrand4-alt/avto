# -*- coding: utf-8 -*-
"""Список из аудита станка по вердиктам: audit_stanka_spisok.py <вердикт|вердикт…>."""
import io
import json
import sys
нужные = set(sys.argv[1].split("|"))
for с in io.open(r"C:\sender\_ops\audit-stanka.jsonl", encoding="utf-8"):
    x = json.loads(с)
    if x["вердикт"] in нужные:
        print("%s | %s | %s | партия %s | нужно %s, предложено %s | %s" % (
            x["rid"], x["имя"][:30], x["вердикт"], x.get("станок_партии"), x["нужно"],
            x["предложено"], x["почему"]))
print("=== СПИСОК ===")
