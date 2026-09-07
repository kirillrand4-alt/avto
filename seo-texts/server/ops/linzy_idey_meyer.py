# -*- coding: utf-8 -*-
"""Нынешние линзы идей: точные строки для правки."""
import io
П = r"C:\sender\sender\ai_quota.py"
стр = io.open(П, encoding="utf-8", errors="replace").read().splitlines()
for i in range(1424, min(1476, len(стр))):
    print("%5d|%s" % (i + 1, стр[i][:170]))
