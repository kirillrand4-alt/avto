# -*- coding: utf-8 -*-
"""Холостой прогон правленой сверки: сколько вердиктов она теперь берёт."""
import subprocess
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
П = r"C:\sender\server\ops\sverka_prigovorov.py"

r = subprocess.run([ПИТОН, П], capture_output=True, text=True, timeout=600,
                   encoding="utf-8", errors="replace")
print("=" * 70)
print("=== СВОДКА: ХОЛОСТОЙ ПРОГОН ПРАВЛЕНОЙ СВЕРКИ ===")
print("код возврата: %s" % r.returncode)
print("")
print("--- вывод ---")
for с in (r.stdout or "").splitlines():
    print("   " + с[:160])
if r.stderr:
    print("--- ошибки ---")
    for с in r.stderr.splitlines()[-12:]:
        print("   " + с[:160])
