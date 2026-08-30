# -*- coding: utf-8 -*-
"""Сколько ключей чеко живо: замер по выборке, а не по всему пулу.

Полная проверка 881 ключа — это 881 запрос, то есть выброшенная суточная
квота двух десятков ключей. Берём равномерную выборку и считаем долю.
"""
import io
import os
import subprocess
import sys
import tempfile

КОРЕНЬ = r"C:\seostat\Parser2"
ФАЙЛ = os.path.join(КОРЕНЬ, "data", "api_keys.txt")
СКОЛЬКО = int(([а.split("=", 1)[1] for а in sys.argv if а.startswith("--n=")]
               or ["40"])[0])

ключи = [с.strip() for с in io.open(ФАЙЛ, encoding="utf-8", errors="replace")
         if с.strip() and not с.strip().startswith("#")]
print("ключей в пуле: %d, проверяю выборку из %d" % (len(ключи), СКОЛЬКО))
шаг = max(1, len(ключи) // СКОЛЬКО)
выборка = ключи[::шаг][:СКОЛЬКО]

врем = os.path.join(tempfile.gettempdir(), "checko-sample-keys.txt")
with io.open(врем, "w", encoding="utf-8") as f:
    f.write("\n".join(выборка))
    f.flush()
    os.fsync(f.fileno())

r = subprocess.run([os.path.join(КОРЕНЬ, ".venv", "Scripts", "python.exe"),
                    os.path.join(КОРЕНЬ, "scripts", "check_keys.py"),
                    "--keys-file", врем],
                   capture_output=True, text=True, timeout=900, cwd=КОРЕНЬ)
try:
    os.remove(врем)
except OSError:
    pass
вывод = (r.stdout or "") + (r.stderr or "")
хвост = вывод.strip().splitlines()
for с in хвост[-25:]:
    print("   %s" % с[:150])

живых = sum(1 for с in хвост if "alive" in с or "жив" in с.lower())
лимит = sum(1 for с in хвост if "limit" in с or "лимит" in с.lower())
print("\n=== ОЦЕНКА ПО ВЫБОРКЕ ===")
print("в выборке %d: похоже живых %d, в лимите %d"
      % (len(выборка), живых, лимит))
if выборка:
    print("экстраполяция на пул %d: живых ≈ %d"
          % (len(ключи), int(len(ключи) * живых / float(len(выборка)))))
