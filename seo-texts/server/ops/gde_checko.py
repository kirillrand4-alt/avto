# -*- coding: utf-8 -*-
"""Какой инструмент по checko уже есть на сервере и как он устроен."""
import io
import os
найдено = []
for корень in (r"C:\sender\_ops", r"C:\sender\server\ops", r"C:\sender\sender",
               r"C:\sender\server"):
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              "web", "tests")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if "checko" in т.lower():
                найдено.append((п, len(т), т.lower().count("checko")))
найдено.sort(key=lambda x: -x[2])
print("файлов с упоминанием checko: %d" % len(найдено))
for п, размер, n in найдено[:22]:
    print("   %-58s %6d б, упоминаний %d" % (п.replace("C:\\sender\\", ""),
                                             размер, n))
print("\n=== ключ и лимиты в окружении ===")
for k in sorted(os.environ):
    if "CHECKO" in k.upper() or "DADATA" in k.upper():
        print("   %s = задан" % k)
