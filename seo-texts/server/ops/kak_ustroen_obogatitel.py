# -*- coding: utf-8 -*-
import io, re
п = r"C:\sender\server\enrich_contacts.py"
т = io.open(п, encoding="utf-8", errors="ignore").read()
print("размер %d знаков, строк %d" % (len(т), т.count("\n")))
print("\n=== как выбирается операция ===")
for м in re.finditer(r"^.*\bop\b.*$", т, re.M):
    с = м.group(0).strip()
    if ("op ==" in с or 'op=' in с or "get('op'" in с or 'get("op"' in с
            or "ОПЕРАЦИИ" in с or "OPS" in с) and len(с) < 130:
        print("   %s" % с[:120])
print("\n=== функции с checko в имени ===")
for м in re.finditer(r"^def\s+([a-zA-Z0-9_]+)", т, re.M):
    if "checko" in м.group(1).lower() or "okved" in м.group(1).lower():
        print("   %s" % м.group(1))
print("\n=== словарь операций, если он есть ===")
for м in re.finditer(r"^(ОПЕРАЦИИ|OPS|HANDLERS|_OPS)\s*[:=]", т, re.M):
    i = м.start()
    print(т[i:i + 900])
    break
