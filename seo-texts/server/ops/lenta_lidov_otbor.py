# -*- coding: utf-8 -*-
"""По какому признаку лента лидов отбирает и что за статусы бывают."""
import io
import os
import re
import sqlite3
from collections import Counter

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
статусы = Counter()
виды = Counter()
for с, в in c.execute("SELECT status, reply_kind FROM leads"):
    статусы[с or "(пусто)"] += 1
    виды[в or "(пусто)"] += 1
c.close()

print("=== СТАТУСЫ ЛИДОВ ===")
for к, в in статусы.most_common():
    print("   %-18s %5d" % (к, в))
print("")
print("=== ВИДЫ ОТВЕТА ===")
for к, в in виды.most_common():
    print("   %-18s %5d" % (к, в))

print("")
print("=== ГДЕ В КОДЕ ЛЕНТА ОТБИРАЕТ ЛИДЫ ===")
for корень in (r"C:\sender\sender", r"C:\sender\web"):
    for путь, кат, файлы in os.walk(корень):
        кат[:] = [d for d in кат if d not in ("__pycache__", ".venv", "tests",
                                              "node_modules", "dist")]
        for имя in файлы:
            if not имя.endswith((".py", ".ts", ".tsx", ".js")):
                continue
            п = os.path.join(путь, имя)
            try:
                т = io.open(п, encoding="utf-8", errors="replace").read()
            except Exception:                                  # noqa: BLE001
                continue
            for м in re.finditer(r"FROM\s+leads[^;]{0,220}", т, re.I | re.S):
                кусок = " ".join(м.group(0).split())[:200]
                if "WHERE" in кусок.upper() or "status" in кусок:
                    print("   %s:%d| %s"
                          % (п.replace("C:\\", ""),
                             т[:м.start()].count("\n") + 1, кусок))
            for м in re.finditer(r"not_interested", т):
                н = т.rfind("\n", 0, м.start()) + 1
                к2 = т.find("\n", м.end())
                print("   %s:%d| %s"
                      % (п.replace("C:\\", ""), т[:м.start()].count("\n") + 1,
                         т[н:к2].strip()[:150]))
