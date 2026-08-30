# -*- coding: utf-8 -*-
"""Обогатители чеко через пул прокси: кто, чем ходит, что достаёт."""
import io, os, re
ФАЙЛЫ = []
for корень in (r"C:\sender", r"C:\seostat"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              ".git", ".venv", "venv")]
        for имя in файлы:
            if re.search(r"prox", имя, re.I) and имя.endswith((".txt", ".json")):
                п = os.path.join(путь, имя)
                try:
                    строки = [с.strip() for с in io.open(п, encoding="utf-8",
                                                         errors="ignore")
                              if с.strip() and not с.strip().startswith("#")]
                except Exception:
                    строки = []
                ФАЙЛЫ.append((п, len(строки),
                              (строки[0][:34] + "…") if строки else ""))

ИНТЕРЕС = [r"C:\sender\server\ops\checko_finansy.py",
           r"C:\sender\server\park_checko_sbor.py",
           r"C:\sender\_tmp\_spr_checko2.py"]
for п in ИНТЕРЕС:
    if not os.path.exists(п):
        print("### %s — нет" % п)
        continue
    т = io.open(п, encoding="utf-8", errors="ignore").read()
    print("\n" + "=" * 72)
    print("### %s (%d б)" % (п.replace("C:\\", ""), len(т)))
    д = re.findall(r'"""(.{0,700}?)"""', т, re.S)
    if д:
        print(д[0].strip()[:700])
    print("--- ключевые константы ---")
    for м in re.finditer(r"^[A-ZА-Я_]{2,24}\s*=\s*.{0,90}$", т, re.M):
        с = м.group(0).strip()
        if re.search(r"prox|PROX|URL|ЖУРНАЛ|ПОТОК|ЛИМИТ|ПАУЗА|DELAY|THREAD|"
                     r"BASE|DB|OUT", с, re.I):
            print("   %s" % с[:96])
    print("--- что достаёт (регулярки полей) ---")
    for м in re.finditer(r"^([A-ZА-Я_]{3,18})\s*=\s*re\.compile\((.{0,70})", т, re.M):
        print("   %-14s %s" % (м.group(1), м.group(2)[:64]))

print("\n" + "=" * 72)
print("=== ФАЙЛЫ ПРОКСИ ===")
for п, n, обр in sorted(ФАЙЛЫ, key=lambda x: -x[1])[:12]:
    print("   %-56s %4d строк  %s" % (п.replace("C:\\", ""), n, обр))
