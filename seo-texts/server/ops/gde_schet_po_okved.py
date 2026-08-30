# -*- coding: utf-8 -*-
"""Ищем скрипт, который считает по чеко, СКОЛЬКО компаний бывает вообще."""
import io, os, re
СЛОВА = ("checko.ru/search", "/search?", "filtr", "фильтр", "найдено",
         "Найдено", "всего компаний", "количество компаний", "total",
         "okved=", "по ОКВЭД", "сколько компаний")
кандидаты = []
for корень in (r"C:\sender\_ops", r"C:\sender\server", r"C:\seostat"):
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              ".git", ".venv", "venv", "web")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            низ = т.lower()
            if "checko" not in низ:
                continue
            очки = sum(1 for с in СЛОВА if с.lower() in низ)
            if очки >= 2:
                кандидаты.append((очки, п, т))
кандидаты.sort(key=lambda x: -x[0])
print("кандидатов: %d" % len(кандидаты))
for очки, п, т in кандидаты[:8]:
    док = re.findall(r'"""(.{0,340}?)"""', т, re.S)
    print("\n=== %s (очков %d, %d б) ===" % (п.replace("C:\\", ""), очки, len(т)))
    if док:
        print("   %s" % " ".join(док[0].split())[:320])
    for м in re.finditer(r"https?://[^\s'\"]{0,90}checko[^\s'\"]{0,60}", т):
        print("   URL: %s" % м.group(0)[:110])
        break
