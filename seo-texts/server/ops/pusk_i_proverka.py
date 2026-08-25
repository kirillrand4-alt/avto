# -*- coding: utf-8 -*-
"""Пустить блок КЦ и через минуту проверить, что письма ложатся в pending.

Раньше генератор отчитывался «ОК», а карточка оставалась снятой. Теперь
очередь оживляет снятую карточку и отдаёт фактический статус — проверяем
это на живых письмах, а не на слово.
"""
import io
import json
import os
import re
import sqlite3
import subprocess
import time

КАТАЛОГ = r"C:\sender\_ops"
ПИТОН = r"C:\Program Files\Python311\python.exe"
лог = os.path.join(КАТАЛОГ, "ochered2508-blok2d-kc.log")

# уже запущенные добиваем, чтобы не плодить параллельные прогоны
в = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"name like '%python%'\" | "
     "Where-Object {$_.CommandLine -like '*partiya_gen*'} | "
     "Select-Object ProcessId | ConvertTo-Json -Compress"],
    capture_output=True, timeout=60)
т = (в.stdout or b"").decode("utf-8", "replace").strip()
if т:
    д = json.loads(т)
    for п in (д if isinstance(д, list) else [д]):
        subprocess.run(["taskkill", "/PID", str(п["ProcessId"]), "/F"],
                       capture_output=True, timeout=30)
        print("остановлен прежний pid %s" % п["ProcessId"])

аргументы = [os.path.join(КАТАЛОГ, "partiya_gen.py"), "2300", "46000", "kc",
             "0", "porog=2.50", "model=claude-sonnet-4-6", "--bez-predklassa"]
команда = ("Start-Process -FilePath '%s' -ArgumentList '%s' "
           "-WorkingDirectory '%s' -WindowStyle Hidden "
           "-RedirectStandardOutput '%s' -RedirectStandardError '%s'"
           % (ПИТОН, "','".join(аргументы), КАТАЛОГ, лог, лог + ".err"))
з = subprocess.run(["powershell", "-NoProfile", "-Command", команда],
                   capture_output=True, timeout=60)
print("пуск: rc=%s %s" % (з.returncode,
                          (з.stdout or з.stderr).decode("cp866", "replace")[:120]))
print("жду первые письма...")
time.sleep(150)

ст = io.open(лог, encoding="utf-8", errors="replace").read().splitlines() \
    if os.path.exists(лог) else []
print("\nлог: %d строк" % len(ст))
for с in ст[-6:]:
    print("   %s" % с[:140])
ид = [int(м.group(1)) for м in
      (re.search(r"#(\d+)\s*$", с.strip()) for с in ст) if м]
print("\nписем поставлено: %d" % len(ид))
if ид:
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    c.row_factory = sqlite3.Row
    from collections import Counter
    св = Counter()
    for н in ид[-20:]:
        р = c.execute("SELECT cr.status cs, COALESCE(m.status,'нет') ms "
                      "  FROM confirm_reviews cr "
                      "  LEFT JOIN messages m ON m.id=cr.message_id "
                      " WHERE cr.id=?", (н,)).fetchone()
        св["карта %s / письмо %s" % (р["cs"], р["ms"]) if р else "карточки нет"] += 1
    print("состояние последних карточек:")
    for к, н in св.most_common():
        print("   %-40s %3d" % (к, н))
