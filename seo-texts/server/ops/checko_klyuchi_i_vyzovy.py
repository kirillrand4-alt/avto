# -*- coding: utf-8 -*-
"""Кто зовёт поиск по ОКВЭД и есть ли ключ к API чеко."""
import io, os, re
корень = r"C:\seostat\Parser2"
print("=== кто зовёт search/extract_search_total ===")
for путь, кат, файлы in os.walk(корень):
    кат[:] = [d for d in кат if d not in ("__pycache__", ".venv", "venv")]
    for имя in файлы:
        if not имя.endswith(".py"):
            continue
        п = os.path.join(путь, имя)
        т = io.open(п, encoding="utf-8", errors="ignore").read()
        if re.search(r"extract_search_total|search_okved|by_okved|SEARCH_URL", т):
            print("   %s" % п.replace("C:\\", ""))
            for i, с in enumerate(т.split("\n")):
                if re.search(r"extract_search_total|search\(|by_okved|SEARCH_URL", с):
                    print("      %4d| %s" % (i + 1, с.strip()[:100]))
print("\n=== файлы с ключами ===")
for путь, кат, файлы in os.walk(r"C:\seostat"):
    кат[:] = [d for d in кат if d not in ("__pycache__", ".venv", "venv",
                                          "node_modules", ".git")]
    for имя in файлы:
        if re.search(r"(checko|key|klyuch).*\.(txt|env|json)$", имя, re.I):
            п = os.path.join(путь, имя)
            try:
                р = os.path.getsize(п)
                т = io.open(п, encoding="utf-8", errors="ignore").read()
                строк = len([с for с in т.split("\n")
                             if с.strip() and not с.strip().startswith("#")])
                print("   %-60s %6d б, непустых строк %d"
                      % (п.replace("C:\\", ""), р, строк))
            except Exception as ex:
                print("   %s: %s" % (п, ex))
print("\n=== функция extract_search_total ===")
т = io.open(r"C:\seostat\Parser2\metalparser\checko.py", encoding="utf-8",
            errors="ignore").read().split("\n")
for i in range(342, 372):
    print("%4d| %s" % (i + 1, т[i][:112]))
