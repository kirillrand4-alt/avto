# -*- coding: utf-8 -*-
"""Замер ключей правильно: список берём разбором самого парсера, не построчно.

Первый замер был негодный: я резал api_keys.txt по строкам, а там вперемешку
проза («тариф», «лимит», «после») — она и уходила в проверку, давая 401.
"""
import io
import os
import subprocess
import sys
import tempfile

КОРЕНЬ = r"C:\seostat\Parser2"
sys.path.insert(0, КОРЕНЬ)
ФАЙЛ = os.path.join(КОРЕНЬ, "data", "api_keys.txt")
СКОЛЬКО = int(([а.split("=", 1)[1] for а in sys.argv if а.startswith("--n=")]
               or ["30"])[0])

sys.path.insert(0, os.path.join(КОРЕНЬ, ".venv", "Lib", "site-packages"))
from metalparser.checko import read_keys_file, _parse_keys   # noqa: E402

сырое = read_keys_file(ФАЙЛ)
ключи = list(dict.fromkeys(_parse_keys(сырое)))
print("строк в файле: %d; ключей после разбора: %d"
      % (sum(1 for _ in io.open(ФАЙЛ, encoding="utf-8", errors="replace")),
         len(ключи)))
print("длины ключей: %s" % sorted({len(к) for к in ключи}))

шаг = max(1, len(ключи) // СКОЛЬКО)
выборка = ключи[::шаг][:СКОЛЬКО]
врем = os.path.join(tempfile.gettempdir(), "checko-vyborka.txt")
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
строки = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
for с in строки[-12:]:
    print("   %s" % с[:150])

def число(метка):
    for с in строки:
        if с.strip().startswith(метка):
            ц = "".join(x for x in с.split(":", 1)[1] if x.isdigit() or x == " ")
            ц = ц.strip().split()
            return int(ц[0]) if ц else 0
    return 0

жив, лим, бит = число("Живых"), число("В лимите"), число("Битых")
print("\n=== ЗАМЕР ПО ВЫБОРКЕ %d ИЗ %d ===" % (len(выборка), len(ключи)))
print("живых %d, в лимите %d, битых %d" % (жив, лим, бит))
if выборка:
    к = len(ключи) / float(len(выборка))
    print("экстраполяция на пул: живых ≈ %d, в лимите ≈ %d, битых ≈ %d"
          % (жив * к, лим * к, бит * к))
    print("запросов в день при 100 на ключ: ≈ %d" % int(жив * к * 100))
