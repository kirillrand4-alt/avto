# -*- coding: utf-8 -*-
import io
п = r"C:\sender\_ops\_ops_dadata_req.py"
стр = io.open(п, encoding="utf-8", errors="ignore").read().split("\n")
print("### %d строк" % len(стр))
for i, с in enumerate(стр):
    print("%4d| %s" % (i + 1, с[:118]))
