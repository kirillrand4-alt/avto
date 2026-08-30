# -*- coding: utf-8 -*-
"""Замер только по настоящим ключам (16 символов, латиница+цифры)."""
import io
import os
import re
import subprocess
import sys
import tempfile

КОРЕНЬ = r"C:\seostat\Parser2"
sys.path.insert(0, КОРЕНЬ)
ФАЙЛ = os.path.join(КОРЕНЬ, "data", "api_keys.txt")
СКОЛЬКО = int(([а.split("=", 1)[1] for а in sys.argv if а.startswith("--n=")]
               or ["30"])[0])
from metalparser.checko import read_keys_file, _parse_keys   # noqa: E402

ключи = [к for к in dict.fromkeys(_parse_keys(read_keys_file(ФАЙЛ)))
         if re.fullmatch(r"[A-Za-z0-9]{16}", к)]
print("настоящих ключей в пуле: %d, проверяю %d" % (len(ключи), СКОЛЬКО))
шаг = max(1, len(ключи) // СКОЛЬКО)
выборка = ключи[::шаг][:СКОЛЬКО]

врем = os.path.join(tempfile.gettempdir(), "checko-16.txt")
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
for с in строки[-10:]:
    print("   %s" % с[:150])


def число(метка):
    for с in строки:
        if с.strip().startswith(метка):
            ц = [x for x in re.findall(r"\d+", с.split(":", 1)[1])]
            return int(ц[0]) if ц else 0
    return 0


жив, лим, бит = число("Живых"), число("В лимите"), число("Битых")
к = len(ключи) / float(len(выборка) or 1)
print("\n=== ЗАМЕР %d ИЗ %d ===" % (len(выборка), len(ключи)))
print("живых %d, в лимите %d, битых %d" % (жив, лим, бит))
print("экстраполяция: живых ≈ %d, в лимите ≈ %d, битых ≈ %d"
      % (жив * к, лим * к, бит * к))
print("суточный потолок при 100 запросах на ключ: ≈ %d запросов"
      % int((жив + лим) * к * 100))
