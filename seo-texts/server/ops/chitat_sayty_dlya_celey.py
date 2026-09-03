# -*- coding: utf-8 -*-
"""Как устроен sayty_dlya_celey.py и find_site_via_xmlriver."""
import io
import os
import re

for П in (r"C:\sender\server\ops\sayty_dlya_celey.py",
          r"C:\sender\server\sayty_dlya_celey.py"):
    if os.path.exists(П):
        break
else:
    П = None

if П:
    т = io.open(П, encoding="utf-8", errors="replace").read()
    стр = т.splitlines()
    print("=== %s: %d строк ===" % (П, len(стр)))
    м = re.search(r'"""(.*?)"""', т, re.S)
    print(м.group(1).strip()[:2000] if м else "шапки нет")
    print("")
    print("--- функции и аргументы ---")
    for м2 in re.finditer(r"^def\s+([\w]+)\(([^)]{0,70})", т, re.M):
        print("   %s(%s)" % (м2.group(1), м2.group(2)[:60]))
    for м3 in re.finditer(r"sys\.argv[^\n]{0,90}", т):
        print("   арг: %s" % м3.group(0)[:100])
else:
    print("sayty_dlya_celey.py не найден")

# сама функция поиска
E = r"C:\sender\server\enrich_contacts.py"
т2 = io.open(E, encoding="utf-8", errors="replace").read()
i = т2.find("def find_site_via_xmlriver")
print("")
print("=== find_site_via_xmlriver ===")
if i >= 0:
    j = т2.find("\ndef ", i + 10)
    кусок = т2[i:j if j > 0 else i + 3000]
    кусок = re.sub(r"(user|key)=\{?[\w\.\[\]'\"]*(KEY|USER)[\w\.\[\]'\"]*\}?",
                   r"\1=<скрыто>", кусок)
    print(кусок[:2600])
else:
    print("не нашлась в enrich_contacts.py")
