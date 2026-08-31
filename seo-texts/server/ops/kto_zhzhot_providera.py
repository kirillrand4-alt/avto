# -*- coding: utf-8 -*-
"""Кто сейчас ходит к провайдеру: процессы, свежие логи, расход по журналам."""
import glob
import io
import json
import os
import subprocess
import time
from collections import Counter, defaultdict

print("=== ВСЕ ПИТОНОВСКИЕ ПРОЦЕССЫ ===")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "ForEach-Object { \"$($_.ProcessId)`t$($_.CreationDate)`t"
                    "$($_.CommandLine)\" }"],
                   capture_output=True, text=True, timeout=120)
строки = [с for с in (r.stdout or "").splitlines() if с.strip()]
for с in строки:
    ч = с.split("\t")
    if len(ч) >= 3:
        print("   pid %-8s %s" % (ч[0].strip(), ч[2].strip()[:150]))
    else:
        print("   %s" % с.strip()[:170])
print("   всего питонов: %d" % len(строки))

print("\n=== ЛОГИ, КОТОРЫЕ РАСТУТ ПРЯМО СЕЙЧАС ===")
сейчас = time.time()
кандидаты = []
for шаблон in (r"C:\sender\_ops\*.log", r"C:\sender\_ops\*.jsonl",
               r"C:\sender\*.log"):
    for п in glob.glob(шаблон):
        try:
            м = os.path.getmtime(п)
        except OSError:
            continue
        if сейчас - м < 900:
            кандидаты.append((м, п, os.path.getsize(п)))
for м, п, размер in sorted(кандидаты, reverse=True)[:14]:
    print("   %-52s %8d Б  %.1f мин назад"
          % (os.path.basename(п), размер, (сейчас - м) / 60.0))

print("\n=== РАСХОД ПО ЖУРНАЛУ ГЕНЕРАЦИИ ЗА ПОСЛЕДНИЙ ЧАС ===")
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
модели = Counter()
деньги = defaultdict(float)
писем = 0
if os.path.exists(ЖУРНАЛ):
    with io.open(ЖУРНАЛ, encoding="utf-8") as f:
        хвост = f.readlines()[-800:]
    for с in хвост:
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        if z.get("этап") != "итог":
            continue
        м = str(z.get("модель") or "?")
        модели[м] += 1
        for поле in ("цена_$", "цена_письма_$", "цена_проверок_$"):
            v = z.get(поле)
            if isinstance(v, (int, float)):
                деньги[поле] += float(v)
        писем += 1
print("   писем в хвосте журнала: %d" % писем)
for м, n in модели.most_common():
    print("   модель %-24s %5d писем" % (м, n))
for поле, v in деньги.items():
    print("   %-18s $%.2f" % (поле, v))

print("\n=== ПОСЛЕДНИЕ 10 СТРОК ЖУРНАЛА: ВРЕМЯ И МОДЕЛЬ ===")
if os.path.exists(ЖУРНАЛ):
    with io.open(ЖУРНАЛ, encoding="utf-8") as f:
        хвост = f.readlines()[-10:]
    for с in хвост:
        try:
            z = json.loads(с)
        except Exception:                                     # noqa: BLE001
            continue
        print("   %-8s %-26s %-18s $%s"
              % (str(z.get("этап"))[:8], str(z.get("имя") or "")[:26],
                 str(z.get("модель") or "")[:18], z.get("цена_$")))

print("\n=== ИТОГ ===")
ген = [с for с in строки if "partiya_gen" in с or "peregen" in с]
print("процессов генерации: %d" % len(ген))
for с in ген:
    ч = с.split("\t")
    print("   %s" % (ч[2].strip()[:150] if len(ч) >= 3 else с.strip()[:150]))
