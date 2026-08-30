# -*- coding: utf-8 -*-
"""Готовый сборщик компаний по ОКВЭД: кто уже листает страницы поиска."""
import io, os, re
ПРИЗНАКИ = (re.compile(r"extract_search_records|Записи"),
            re.compile(r"page\s*[+=]|СтрВсего|page=\d|страниц", re.I),
            re.compile(r"okved|ОКВЭД", re.I))
итог = []
for корень in (r"C:\seostat", r"C:\sender"):
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              ".git", ".venv", "venv",
                                              "sp2_pages")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            try:
                if os.path.getsize(п) > 300000:
                    continue
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if "checko" not in т.lower():
                continue
            очки = sum(1 for пр in ПРИЗНАКИ if пр.search(т))
            if очки >= 2:
                итог.append((очки, len(т), п, т))
итог.sort(key=lambda x: (-x[0], x[1]))
print("кандидатов: %d" % len(итог))
for очки, размер, п, т in итог[:10]:
    док = re.findall(r'"""(.{0,320}?)"""', т, re.S)
    print("\n=== %s (%d б, очков %d) ===" % (п.replace("C:\\", ""), размер, очки))
    if док:
        print("   %s" % " ".join(док[0].split())[:300])
    for м in re.finditer(r"^\s*(?:def|OUT|ЖУРНАЛ|OUTPUT|SAVE)[^\n]{0,90}", т, re.M):
        с = м.group(0).strip()
        if с.startswith(("def ", "OUT", "ЖУРНАЛ", "OUTPUT", "SAVE")):
            print("      %s" % с[:88])
