# -*- coding: utf-8 -*-
import io
п = r"C:\sender\_ops\park_1s_checko_kartochka.py"
стр = io.open(п, encoding="utf-8", errors="ignore").read().split("\n")
print("### %s (%d строк)" % (п, len(стр)))
for i, с in enumerate(стр[:96]):
    print("%4d| %s" % (i + 1, с[:114]))
