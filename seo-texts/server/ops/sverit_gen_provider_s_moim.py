# -*- coding: utf-8 -*-
"""Diff моей копии gen_provider.py с боевой (она лежит в C:\\sender, не в пакете)."""
import difflib
import io
import os

боевой = r"C:\sender\gen_provider.py"
моё = r"C:\sender\_ops\MOYO-gen_provider.py"
a = io.open(боевой, encoding="utf-8", errors="replace").read().splitlines()
b = io.open(моё, encoding="utf-8", errors="replace").read().splitlines()
print(f"сервер: {len(a)} строк | моё: {len(b)} строк")
diff = list(difflib.unified_diff(a, b, fromfile="СЕРВЕР", tofile="МОЁ",
                                 lineterm="", n=2))
print(f"различий в diff: {len(diff)} строк")
for с in diff[:200]:
    print(с)
