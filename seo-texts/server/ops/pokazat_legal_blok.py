# -*- coding: utf-8 -*-
import io
т = io.open(r"C:\sender\sender.yaml", encoding="utf-8").read().split("\n")
for i in range(10, 34):
    print("%4d| %s" % (i + 1, т[i]))
print("   ...")
for i in range(386, 430):
    print("%4d| %s" % (i + 1, т[i]))
