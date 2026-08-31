# -*- coding: utf-8 -*-
"""Только чтение: предполётная перед прогоном партии (§7 Шаг 0)."""
import glob
import hashlib
import os
import subprocess

print("=== 1. ИДЁТ ЛИ ЧУЖОЙ ПРОГОН ===")
try:
    p = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
         "Select-Object ProcessId,CreationDate,CommandLine | Format-List"],
        capture_output=True, text=True, timeout=90)
    строки = [x for x in (p.stdout or "").splitlines() if x.strip()]
    свои = [x for x in строки if "partiya_gen" in x or "pustit" in x]
    print("  процессов python в выводе: %d строк" % len(строки))
    if свои:
        print("  !!! НАЙДЕН ПРОГОН:")
        for x in свои:
            print("     ", x.strip()[:200])
    else:
        print("  чужого partiya_gen НЕ идёт")
except Exception as ex:
    print("  не смог опросить процессы: %s" % str(ex)[:100])

print("\n=== 2. ГДЕ ЛЕЖИТ partiya_gen И ЕГО SHA1 ===")
for путь in (r"C:\sender\_ops\partiya_gen.py",
             r"C:\sender\server\ops\partiya_gen.py"):
    if os.path.exists(путь):
        b = open(путь, "rb").read()
        print("  %s\n     %d байт, sha1 %s, строк %d"
              % (путь, len(b), hashlib.sha1(b).hexdigest(), b.count(b"\n") + 1))
    else:
        print("  %s — нет" % путь)

print("\n=== 3. СВЕЖИЕ ЛОГИ ПРОГОНОВ ===")
логи = sorted(glob.glob(r"C:\sender\_ops\partiya_gen-*.log"),
              key=os.path.getmtime, reverse=True)[:5]
import datetime
for л in логи:
    т = datetime.datetime.fromtimestamp(os.path.getmtime(л))
    print("  %s  %8d б  %s" % (т.strftime("%m-%d %H:%M"), os.path.getsize(л),
                               os.path.basename(л)))

print("\n=== 4. ЕСТЬ ЛИ ЗАПУСКАЛКА ===")
for имя in ("pustit_otceplenno.py",):
    for кат in (r"C:\sender\_ops", r"C:\sender\server\ops"):
        п = os.path.join(кат, имя)
        print("  %s: %s" % (п, "есть" if os.path.exists(п) else "нет"))

print("\n=== ИТОГ ПРЕДПОЛЁТНОЙ ===")
print("  (см. пункты 1-4 выше)")
