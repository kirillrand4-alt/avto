# -*- coding: utf-8 -*-
"""Где лежат ключи чеко и сколько их живо прямо сейчас."""
import io
import os
import re

КОРЕНЬ = r"C:\seostat\Parser2"
print("=== scripts/check_keys.py (первые 70 строк) ===")
п = os.path.join(КОРЕНЬ, "scripts", "check_keys.py")
for i, с in enumerate(io.open(п, encoding="utf-8", errors="replace")):
    if i >= 70:
        break
    print("   %s" % с.rstrip()[:140])

print("\n=== где в коде упоминается пул/лимит ключей ===")
for корень, папки, файлы in os.walk(КОРЕНЬ):
    папки[:] = [d for d in папки if d not in (".git", ".venv", "__pycache__",
                                              "node_modules", "data")]
    for f in файлы:
        if not f.endswith(".py"):
            continue
        пп = os.path.join(корень, f)
        try:
            т = io.open(пп, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if re.search(r"keys?\.(txt|json|db)|key_pool|KEYS_FILE|api_keys", т):
            for n, с in enumerate(т.splitlines(), 1):
                if re.search(r"keys?\.(txt|json|db)|key_pool|KEYS_FILE|api_keys",
                             с):
                    print("   %s:%d  %s" % (пп.replace(КОРЕНЬ, "…"), n,
                                            с.strip()[:120]))
