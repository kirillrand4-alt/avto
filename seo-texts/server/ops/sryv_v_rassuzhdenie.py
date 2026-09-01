# -*- coding: utf-8 -*-
"""Что значит «срыв в рассуждение даже на low» и на какой модели он ловится."""
import io
import os
import re

П = r"C:\sender\sender\review_lenses.py"
s = io.open(П, encoding="utf-8", errors="replace").read()
print("review_lenses.py: %d байт, %d строк" % (len(s), s.count("\n") + 1))
for м in re.finditer(r"рассужден", s):
    н = s.rfind("\n", 0, max(0, м.start() - 1400))
    к = s.find("\n", м.end() + 700)
    кусок = s[н + 1:к]
    строка = s[:м.start()].count("\n") + 1
    print("")
    print("=== около строки %d ===" % строка)
    print(кусок[-2100:])
    break

print("")
print("=== default_caller целиком ===")
i = s.find("def default_caller")
if i >= 0:
    j = s.find("\ndef ", i + 10)
    print(s[i:j if j > 0 else i + 4000][:4500])
