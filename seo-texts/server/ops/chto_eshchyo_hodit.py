# -*- coding: utf-8 -*-
"""Ходят ли к провайдеру остальные живые процессы."""
import io
import os
import re
import subprocess
import time

for п in (r"C:\sender\_tmp\pr_ochered_meyer.py",
          r"C:\sender\server\enrich_contacts.py",
          r"C:\sender\server\zenno_most.py"):
    print("\n######## %s ########" % os.path.basename(п))
    if not os.path.exists(п):
        print("   файла нет")
        continue
    т = io.open(п, encoding="utf-8", errors="replace").read()
    print("   %d Б, изменён %s" % (os.path.getsize(п),
          time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(п)))))
    зовёт = re.findall(r"(gen_provider|default_caller|router\.cheap|"
                       r"PROVIDER_API_KEY|claude-[a-z0-9.\-]+)", т)
    if зовёт:
        from collections import Counter
        for к, n in Counter(зовёт).most_common(8):
            print("   зовёт %-26s %d раз" % (к, n))
    else:
        print("   провайдера не зовёт")
    # первая строка докстринга
    м = re.search(r'"""(.{0,160})', т, re.S)
    if м:
        print("   назначение: %s" % " ".join(м.group(1).split())[:150])

print("\n=== ПРОЦЕССЫ enrich_contacts: ЧТО ОНИ ДЕЛАЮТ ===")
r = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                    "Where-Object { $_.CommandLine -like '*enrich_contacts*' -or "
                    "$_.CommandLine -like '*pr_ochered*' } | "
                    "ForEach-Object { \"$($_.ProcessId)`t$($_.CreationDate)`t$($_.CommandLine)\" }"],
                   capture_output=True, text=True, timeout=90)
for с in (r.stdout or "").splitlines():
    if с.strip():
        ч = с.split("\t")
        print("   pid %-8s запущен %s" % (ч[0].strip(),
                                          ч[1].strip()[:20] if len(ч) > 1 else "?"))
        if len(ч) > 2:
            print("        %s" % ч[2].strip()[:150])

print("\n=== МОЙ ДОБОР: ЖИВ ЛИ ===")
r2 = subprocess.run(["powershell", "-NoProfile", "-Command",
                     "(Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                     "Where-Object { $_.CommandLine -like '*partiya_gen*' }).Count"],
                    capture_output=True, text=True, timeout=90)
print("   процессов partiya_gen: %s" % (r2.stdout or "").strip())
import glob
логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)[:1]
for л in логи:
    с = io.open(л, encoding="utf-8", errors="replace").read().splitlines()
    for x in с[-6:]:
        print("   %s" % x[:150])
print("\n=== ИТОГ ===")
print("opus сейчас жжёт только partiya_gen (мой добор), если выше 0 процессов")
