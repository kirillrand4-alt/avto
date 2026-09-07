# -*- coding: utf-8 -*-
"""Блок идей захода в ai_quota.py целиком."""
import io
П = r"C:\sender\sender\ai_quota.py"
стр = io.open(П, encoding="utf-8", errors="replace").read().splitlines()
for i in range(1415, min(1560, len(стр))):
    print("%5d| %s" % (i + 1, стр[i][:160]))
