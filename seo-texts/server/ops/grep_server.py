# -*- coding: utf-8 -*-
"""grep по коду панели: grep_server.py <строка> [корень=C:\\sender\\sender]"""
import io, os, sys
ч = sys.argv[1]; корень = sys.argv[2] if len(sys.argv) > 2 else r"C:\sender\sender"
for п, _, фф in os.walk(корень):
    if "node_modules" in п or "__pycache__" in п: continue
    for ф in фф:
        if not ф.endswith((".py", ".html", ".js", ".jsx", ".ts", ".tsx", ".vue", ".css")): continue
        try: т = io.open(os.path.join(п, ф), encoding="utf-8", errors="replace").read()
        except Exception: continue
        for н, s in enumerate(т.splitlines(), 1):
            if ч in s: print("%s:%d: %s" % (os.path.join(п, ф), н, s.strip()[:200]))
