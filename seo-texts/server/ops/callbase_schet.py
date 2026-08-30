# -*- coding: utf-8 -*-
"""Что считает callbase.py и есть ли там «сколько компаний всего по ОКВЭД»."""
import io, re
п = r"C:\seostat\app\services\callbase.py"
т = io.open(п, encoding="utf-8", errors="ignore").read()
стр = т.split("\n")
print("### %s — %d строк" % (п, len(стр)))
инт = re.compile(r"(okved|оквэд|count|скольк|всего|рынок|ёмкост|потенциал|"
                 r"checko|егрюл|EGRUL)", re.I)
показано = 0
for i, с in enumerate(стр):
    if инт.search(с) and not с.strip().startswith("#"):
        print("%5d| %s" % (i + 1, с[:118]))
        показано += 1
    if показано > 60:
        break
print("\n=== функции файла ===")
for м in re.finditer(r"^(?:async )?def\s+([a-zA-Z0-9_]+)\(([^)]{0,70})", т, re.M):
    print("   %s(%s)" % (м.group(1), м.group(2)[:60]))
