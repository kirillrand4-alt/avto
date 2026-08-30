# -*- coding: utf-8 -*-
"""Точный поиск: скрипты с ПОИСКОВЫМ url чеко или разбором «найдено N»."""
import io, os, re
УЗОРЫ = [re.compile(r"checko\.ru/(?!company/)[a-z\-]{2,20}", re.I),
         re.compile(r"Найдено[^\n]{0,40}компан", re.I),
         re.compile(r"(?:всего|итого)[^\n]{0,20}компан\w*\s*[:=]", re.I),
         re.compile(r"okved[^\n]{0,20}(?:count|скольк|числ)", re.I),
         re.compile(r"рынок|ёмкость|emkost|потенциал", re.I)]
найдено = []
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
            if os.path.getsize(п) > 90000:
                continue
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            попал = [у.pattern[:26] for у in УЗОРЫ if у.search(т)]
            if попал and ("checko" in т.lower() or "оквэд" in т.lower()
                          or "okved" in т.lower()):
                найдено.append((len(попал), п, попал, т))
найдено.sort(key=lambda x: -x[0])
print("подходящих файлов: %d" % len(найдено))
for очки, п, попал, т in найдено[:12]:
    print("\n=== %s ===" % п.replace("C:\\", ""))
    print("   совпало: %s" % ", ".join(попал))
    док = re.findall(r'"""(.{0,300}?)"""', т, re.S)
    if док:
        print("   %s" % " ".join(док[0].split())[:280])
    for м in re.finditer(r"https?://[^\s'\"]{0,100}", т):
        u = м.group(0)
        if "checko" in u and "/company/" not in u:
            print("   URL: %s" % u[:110])
            break
