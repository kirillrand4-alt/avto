# -*- coding: utf-8 -*-
import io, sys
П = r"C:\sender\sender\lid_ssylka.py"
стр = io.open(П, encoding="utf-8").read().split("\n")
a = int(sys.argv[1]) if len(sys.argv) > 1 else 1
b = int(sys.argv[2]) if len(sys.argv) > 2 else len(стр)
for i in range(a - 1, min(b, len(стр))):
    print("%4d| %s" % (i + 1, стр[i]))
print("ВСЕГО СТРОК: %d" % len(стр))
