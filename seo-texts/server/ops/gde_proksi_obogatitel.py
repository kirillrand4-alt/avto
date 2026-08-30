# -*- coding: utf-8 -*-
"""Скрипты, ходящие на чеко через пул прокси, и файлы прокси."""
import io, os, re
print("=== файлы прокси ===")
for корень in (r"C:\sender", r"C:\seostat"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              ".git", ".venv", "venv")]
        for имя in файлы:
            if re.search(r"prox|проксі|proksi", имя, re.I) and \
                    имя.endswith((".txt", ".json", ".csv")):
                п = os.path.join(путь, имя)
                try:
                    строк = sum(1 for с in io.open(п, encoding="utf-8",
                                                   errors="ignore")
                                if с.strip() and not с.strip().startswith("#"))
                except Exception:
                    строк = "?"
                print("   %-58s строк %s" % (п.replace("C:\\", ""), строк))
print("\n=== кто ими пользуется вместе с чеко ===")
for корень in (r"C:\sender", r"C:\seostat"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              ".git", ".venv", "venv")]
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
            низ = т.lower()
            if "prox" in низ and "checko" in низ:
                д = re.findall(r'"""(.{0,220}?)"""', т, re.S)
                print("\n   %s" % п.replace("C:\\", ""))
                if д:
                    print("      %s" % " ".join(д[0].split())[:200])
                for м in re.finditer(r"^[A-ZА-Я_]{3,20}\s*=\s*r?['\"][^'\"]{0,80}prox[^'\"]{0,40}['\"]",
                                     т, re.M | re.I):
                    print("      %s" % м.group(0).strip()[:100])
print("\n=== зенка ===")
д = r"C:\seostat\Parser2\docs\zennoposter_enrich.md"
if os.path.exists(д):
    т = io.open(д, encoding="utf-8", errors="ignore").read()
    print(т[:1500])
