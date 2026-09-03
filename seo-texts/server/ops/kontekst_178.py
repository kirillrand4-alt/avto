# -*- coding: utf-8 -*-
"""Точный контекст вокруг строки 178 sayty_dlya_celey.py."""
import io
П = r"C:\sender\server\ops\sayty_dlya_celey.py"
стр = io.open(П, encoding="utf-8", errors="replace").read().splitlines()
for i in range(160, min(196, len(стр))):
    print("%4d|%s" % (i + 1, стр[i][:150].replace("\t", "    ")))
