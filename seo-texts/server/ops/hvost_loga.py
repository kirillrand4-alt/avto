# -*- coding: utf-8 -*-
"""Хвост файла: hvost_loga.py <путь> [n=40]"""
import io
import os
import sys
П = sys.argv[1]
N = int(dict(а.split("=", 1) for а in sys.argv[2:] if "=" in а).get("n", "40"))
with io.open(П, "rb") as f:
    f.seek(max(0, os.path.getsize(П) - 200000))
    стр = f.read().decode("utf-8", errors="replace").splitlines()
for с in стр[-N:]:
    print(с[:230])
print("=== ХВОСТ ===")
