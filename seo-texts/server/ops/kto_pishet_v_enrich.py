# -*- coding: utf-8 -*-
"""Кто непрерывно пишет в enrich.db: ищем в коде соседних служб."""
import io, os, re, subprocess, time
корни = [r"C:\seostat", r"C:\sender\server"]
найдено = []
for корень in корни:
    if not os.path.isdir(корень):
        continue
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", "node_modules",
                                              ".git", ".venv", "venv", "data")]
        for имя in файлы:
            if not имя.endswith(".py"):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            if "enrich.db" in т:
                пишет = bool(re.search(r"\b(INSERT|UPDATE|DELETE|insert |update )",
                                       т, re.I))
                найдено.append((п, пишет, т.count("enrich.db")))
найдено.sort(key=lambda x: (not x[1], -x[2]))
print("файлов, знающих про enrich.db: %d" % len(найдено))
for п, пишет, n in найдено[:16]:
    print("   %-62s %s упоминаний %d"
          % (п.replace("C:\\", ""), "ПИШЕТ" if пишет else "читает", n))
print("\n=== размер WAL сейчас ===")
for п in (r"C:\sender\enrich.db-wal", r"C:\sender\enrich.db-shm"):
    if os.path.exists(п):
        print("   %-24s %8.1f МБ  изменён %s"
              % (os.path.basename(п), os.path.getsize(п) / 1048576,
                 time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(п)))))
print("   сейчас %s" % time.strftime("%H:%M:%S"))
