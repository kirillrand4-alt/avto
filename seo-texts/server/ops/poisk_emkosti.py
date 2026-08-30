# -*- coding: utf-8 -*-
"""Ищем что угодно, что считает КОЛИЧЕСТВО компаний по ОКВЭД во внешнем источнике."""
import io, os, re
ИСТОЧНИКИ = ("rusprofile", "list-org", "zachestnyibiznes", "sbis.ru", "audit-it",
             "vypiska", "egrul.nalog", "checko", "spark", "seldon", "kartoteka",
             "vyborka", "выборка", "фильтр компаний")
СЧЁТ = re.compile(r"(найдено|организац\w*\s*[:=]|компани\w*\s*[:=]\s*\d|"
                  r"\bcount\b|\btotal\b|кол-?во|количество)", re.I)
ОКВЭД = re.compile(r"okved|оквэд", re.I)
итог = []
for корень in (r"C:\sender", r"C:\seostat"):
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              ".git", ".venv", "venv", "web",
                                              "sp2_pages", "data")]
        for имя in файлы:
            if not имя.endswith((".py", ".md")):
                continue
            п = os.path.join(путь, имя)
            try:
                if os.path.getsize(п) > 200000:
                    continue
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            низ = т.lower()
            ист = [и for и in ИСТОЧНИКИ if и in низ]
            if not ист or not ОКВЭД.search(т) or not СЧЁТ.search(т):
                continue
            # нужен внешний запрос
            if not re.search(r"requests\.|urllib|httpx|aiohttp|http", низ):
                continue
            итог.append((len(ист), п, ист, т))
итог.sort(key=lambda x: -x[0])
print("кандидатов: %d" % len(итог))
for очки, п, ист, т in итог[:14]:
    док = re.findall(r'"""(.{0,260}?)"""', т, re.S)
    print("\n=== %s ===" % п.replace("C:\\", ""))
    print("   источники: %s" % ", ".join(ист[:5]))
    if док:
        print("   %s" % " ".join(док[0].split())[:250])
