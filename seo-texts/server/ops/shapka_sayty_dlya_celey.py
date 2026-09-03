# -*- coding: utf-8 -*-
"""Шапка и разбор аргументов sayty_dlya_celey.py — формат целей и вывода."""
import io
import os
import re

П = r"C:\sender\server\ops\sayty_dlya_celey.py"
if not os.path.exists(П):
    П = r"C:\sender\server\sayty_dlya_celey.py"
т = io.open(П, encoding="utf-8", errors="replace").read()
стр = т.splitlines()
print("=== %s ===" % П)
for i, с in enumerate(стр[:70], 1):
    print("%4d| %s" % (i, с[:150]))
print("")
print("--- где читает цели и куда пишет ---")
for м in re.finditer(r"^.{0,120}(targets|ЦЕЛИ|jsonl|open\(|json\.dump|"
                     r"EDB|requisites|companies).{0,90}$", т, re.M):
    с = м.group(0).strip()
    if с and not с.startswith("#"):
        print("   " + с[:150])
