# -*- coding: utf-8 -*-
"""grep по коду панели на сервере: grep_servera.py "<regex>" [kontekst=3]"""
import glob
import io
import re
import sys
R = re.compile(sys.argv[1])
K = int(dict(а.split("=", 1) for а in sys.argv[2:] if "=" in а).get("kontekst", "3"))
for п in [x for x in glob.glob(r"C:\sender\sender\**\*", recursive=True) if x.endswith((".py", ".js", ".html", ".jsx", ".ts"))]:
    стр = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    for i, с in enumerate(стр):
        if R.search(с):
            print("--- %s:%d" % (п.split("\\")[-1], i + 1))
            for j in range(max(0, i - K), min(len(стр), i + K + 1)):
                print("  %5d %s" % (j + 1, стр[j][:170]))
print("=== GREP ===")
