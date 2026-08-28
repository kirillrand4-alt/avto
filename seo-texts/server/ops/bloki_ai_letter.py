# -*- coding: utf-8 -*-
import hashlib, io
т = io.open(r"C:\sender\sender\ai_letter.py", encoding="utf-8").read().split("\n")
print("строк: %d" % len(т))
for i in range(0, len(т), 200):
    b = "\n".join(т[i:i + 200]).encode("utf-8")
    print("%5d-%5d %s" % (i + 1, min(i + 200, len(т)), hashlib.sha256(b).hexdigest()[:12]))
