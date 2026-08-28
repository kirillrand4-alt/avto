# -*- coding: utf-8 -*-
import io
П = r"C:\sender\sender\lid_ssylka.py"
стр = io.open(П, encoding="utf-8").read().split("\n")
for i, s in enumerate(стр):
    if s.startswith("def ") or s.startswith("_") or "ЦИТАТ" in s.upper():
        print("%4d| %s" % (i + 1, s[:120]))
