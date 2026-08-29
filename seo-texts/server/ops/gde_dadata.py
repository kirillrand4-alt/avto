# -*- coding: utf-8 -*-
"""Есть ли готовый инструмент DaData по ИНН и как он пишет результат."""
import io, os, re
кандидаты = []
for корень in (r"C:\sender\_ops", r"C:\sender\server\ops", r"C:\sender\server"):
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "web", "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if "dadata" in т.lower() and "findById" in т:
                кандидаты.append((п, т))
print("файлов с findById DaData: %d" % len(кандидаты))
for п, т in кандидаты[:6]:
    print("\n=== %s ===" % п)
    док = re.findall(r'"""(.{0,420}?)"""', т, re.S)
    if док:
        print("   %s" % " ".join(док[0].split())[:400])
    for м in re.finditer(r"^(ЖУРНАЛ|OUT|ВЫХОД)\s*=.*$", т, re.M):
        print("   %s" % м.group(0).strip()[:100])
    if "enrich" in т.lower():
        print("   пишет в enrich: да")
