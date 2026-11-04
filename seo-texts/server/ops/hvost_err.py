# -*- coding: utf-8 -*-
"""Последние N строк panel_err.log / panel_out.log без фильтра: hvost_err.py [N] [out]"""
import io, os, sys
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60
п = r"C:\sender\_ops\panel_out.log" if "out" in sys.argv else r"C:\sender\_ops\panel_err.log"
р = os.path.getsize(п)
with io.open(п, "rb") as f:
    f.seek(max(0, р - 300_000)); т = f.read().decode("utf-8", "replace").splitlines()
for s in [x for x in т if "GET /api" not in x and "POST /api" not in x][-N:]:
    print(s[:220])
