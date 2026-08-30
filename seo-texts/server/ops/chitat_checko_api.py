# -*- coding: utf-8 -*-
import io, os, re
п = r"C:\seostat\Parser2\metalparser\checko.py"
т = io.open(п, encoding="utf-8", errors="ignore").read()
стр = т.split("\n")
print("### %s — %d строк, %d б" % (п, len(стр), len(т)))
print("\n=== функции ===")
for м in re.finditer(r"^(?:async )?def\s+([a-zA-Z0-9_]+)\(([^)]{0,80})", т, re.M):
    print("   %s(%s)" % (м.group(1), м.group(2)[:70]))
print("\n=== URL и эндпоинты ===")
for м in re.finditer(r"['\"]([^'\"]{0,120}(?:api\.)?checko[^'\"]{0,120})['\"]", т):
    print("   %s" % м.group(1)[:120])
print("\n=== ключи и лимиты ===")
for i, с in enumerate(стр):
    if re.search(r"(key|ключ|limit|лимит|тариф|quota|Исчерпан)", с, re.I) \
            and not с.strip().startswith("#"):
        print("%5d| %s" % (i + 1, с.strip()[:110]))
print("\n=== начало файла ===")
for i, с in enumerate(стр[:40]):
    print("%4d| %s" % (i + 1, с[:112]))
