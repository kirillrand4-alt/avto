# -*- coding: utf-8 -*-
"""Вытащить живой код панели кусками (zlib+base64) — только чтение.

    vytashchit_kod.py full <путь> <кусок>
    vytashchit_kod.py diff <путь> <эталон из ops\\ref> <кусок>
Печатает «КУСОК i/n» и base64-строку; локально склеить и распаковать.
"""
import base64
import difflib
import io
import os
import sys
import zlib

РАЗМ = 5600
режим, путь = sys.argv[1], sys.argv[2]
живой = io.open(путь, encoding="utf-8", errors="replace").read()
if режим == "diff":
    эталон = io.open(os.path.join(r"C:\sender\server\ops\ref", sys.argv[3]),
                     encoding="utf-8", errors="replace").read()
    текст = "".join(difflib.unified_diff(эталон.splitlines(True), живой.splitlines(True),
                                         "repo", "live", n=3))
    кусок = int(sys.argv[4])
else:
    текст = живой
    кусок = int(sys.argv[3])
b = base64.b64encode(zlib.compress(текст.encode("utf-8"), 9)).decode()
n = (len(b) + РАЗМ - 1) // РАЗМ
print("КУСОК %d/%d len=%d" % (кусок, n, len(текст)))
print(b[кусок * РАЗМ:(кусок + 1) * РАЗМ])
