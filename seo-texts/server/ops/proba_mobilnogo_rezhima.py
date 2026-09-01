# -*- coding: utf-8 -*-
"""Короткая проба мобильного режима ходилки: тридцать компаний."""
import subprocess
import time

ПИТОН = r"C:\Program Files\Python311\python.exe"
П = r"C:\sender\_ops\checko_finansy.py"

t0 = time.time()
r = subprocess.run([ПИТОН, П, "--lim", "30", "--potok", "3", "--mobilnye",
                    "--bez-bazy"],
                   capture_output=True, text=True, timeout=780,
                   encoding="utf-8", errors="replace")
print("=" * 74)
print("=== СВОДКА: ПРОБА МОБИЛЬНОГО РЕЖИМА ===")
print("код возврата %s, время %.0f с" % (r.returncode, time.time() - t0))
print("")
print("--- вывод ---")
for с in (r.stdout or "").splitlines():
    print("   " + с[:160])
if r.stderr:
    print("--- ошибки ---")
    for с in r.stderr.splitlines()[-14:]:
        print("   " + с[:160])
