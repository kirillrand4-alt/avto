# -*- coding: utf-8 -*-
"""Все логи сегодняшних блоков и живые процессы — одним взглядом."""
import io
import json
import os
import re
import sqlite3
import subprocess
import time
from collections import Counter

КАТАЛОГ = r"C:\sender\_ops"
сейчас = time.time()
в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*'} | "
     "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
    capture_output=True, timeout=60)
т = (в.stdout or b"").decode("utf-8", "replace").strip()
print("=== ЖИВЫЕ ПРОГОНЫ ===")
if т:
    д = json.loads(т)
    for п in (д if isinstance(д, list) else [д]):
        print("   pid %s: %s" % (п["ProcessId"], str(п["CommandLine"])[:130]))
else:
    print("   НЕТ")

print("\n=== ЛОГИ БЛОКОВ ===")
for имя in sorted(os.listdir(КАТАЛОГ)):
    if not имя.startswith("ochered2508-blok") or имя.endswith(".err"):
        continue
    п = os.path.join(КАТАЛОГ, имя)
    ст = io.open(п, encoding="utf-8", errors="replace").read().splitlines()
    ид = [int(м.group(1)) for м in
          (re.search(r"#(\d+)\s*$", с.strip()) for с in ст) if м]
    итог = next((с.strip() for с in reversed(ст) if с.startswith("итог:")), "")
    print("   %-32s строк %4d, писем %4d, обновлён %5.1f мин назад %s"
          % (имя, len(ст), len(ид), (сейчас - os.path.getmtime(п)) / 60.0,
             ("| " + итог[:50]) if итог else ""))

# Куда легли письма самого свежего блока.
свежий = None
for имя in sorted(os.listdir(КАТАЛОГ)):
    if имя.startswith("ochered2508-blok") and not имя.endswith(".err"):
        свежий = os.path.join(КАТАЛОГ, имя)
if свежий:
    ст = io.open(свежий, encoding="utf-8", errors="replace").read().splitlines()
    ид = [int(м.group(1)) for м in
          (re.search(r"#(\d+)\s*$", с.strip()) for с in ст) if м]
    print("\n=== КУДА ЛЕГЛИ ПИСЬМА %s ===" % os.path.basename(свежий))
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    c.row_factory = sqlite3.Row
    св = Counter()
    for н in ид[-40:]:
        р = c.execute("SELECT cr.status cs, COALESCE(m.status,'нет') ms "
                      "  FROM confirm_reviews cr "
                      "  LEFT JOIN messages m ON m.id=cr.message_id "
                      " WHERE cr.id=?", (н,)).fetchone()
        св["карта %s / письмо %s" % (р["cs"], р["ms"]) if р else "карточки нет"] += 1
    for к, н in св.most_common():
        print("   %-42s %3d" % (к, н))
