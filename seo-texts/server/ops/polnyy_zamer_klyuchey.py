# -*- coding: utf-8 -*-
"""Полная проверка пула ключей чеко + запись живых в отдельный файл.

Зачем полностью: выборка из 30 дала «жив 1, битых 29», и это не суточный
лимит (тот отдаёт 403 со словом «лимит»), а HTTP 401 — ключ недействителен.
Такие к полуночи не воскресают. Нужен точный список живых, чтобы сборщик не
крутил вхолостую четыре сотни мёртвых.

Результат пишем в СЕРВЕРНЫЙ файл (durability), а не только в вывод.
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import time

КОРЕНЬ = r"C:\seostat\Parser2"
sys.path.insert(0, КОРЕНЬ)
ФАЙЛ = os.path.join(КОРЕНЬ, "data", "api_keys.txt")
ЖИВЫЕ = r"C:\sender\_ops\checko-zhivye-klyuchi.txt"
ОТЧЁТ = r"C:\sender\_ops\checko-klyuchi-zamer.jsonl"
from metalparser.checko import read_keys_file, _parse_keys   # noqa: E402

ключи = [к for к in dict.fromkeys(_parse_keys(read_keys_file(ФАЙЛ)))
         if re.fullmatch(r"[A-Za-z0-9]{16}", к)]
print("настоящих ключей: %d — проверяю все" % len(ключи))

врем = os.path.join(tempfile.gettempdir(), "checko-vse.txt")
with io.open(врем, "w", encoding="utf-8") as f:
    f.write("\n".join(ключи))
    f.flush()
    os.fsync(f.fileno())
т0 = time.time()
r = subprocess.run([os.path.join(КОРЕНЬ, ".venv", "Scripts", "python.exe"),
                    os.path.join(КОРЕНЬ, "scripts", "check_keys.py"),
                    "--keys-file", врем],
                   capture_output=True, text=True, timeout=1500, cwd=КОРЕНЬ)
try:
    os.remove(врем)
except OSError:
    pass
строки = ((r.stdout or "") + (r.stderr or "")).splitlines()

хвосты = {"alive": [], "limit": []}
for с in строки:
    м = re.search(r"…([A-Za-z0-9]{4})", с)
    if not м:
        continue
    if "ЖИВ" in с.upper() or "alive" in с:
        хвосты["alive"].append(м.group(1))
    elif "ЛИМИТ" in с.upper() or "limit" in с:
        хвосты["limit"].append(м.group(1))

живые = [к for к in ключи if к[-4:] in set(хвосты["alive"])]
влимите = [к for к in ключи if к[-4:] in set(хвосты["limit"])]
годные = живые + влимите
with io.open(ЖИВЫЕ, "w", encoding="utf-8") as f:
    f.write("\n".join(годные) + ("\n" if годные else ""))
    f.flush()
    os.fsync(f.fileno())
with io.open(ОТЧЁТ, "a", encoding="utf-8") as f:
    f.write('{"ts": %d, "vsego": %d, "zhivyh": %d, "v_limite": %d}\n'
            % (int(time.time()), len(ключи), len(живые), len(влимите)))
    f.flush()
    os.fsync(f.fileno())

for с in строки[-6:]:
    print("   %s" % с[:140])
print("\n=== ИТОГ ПО ПУЛУ ===")
print("всего настоящих ключей: %d" % len(ключи))
print("живых сейчас:           %d" % len(живые))
print("в суточном лимите:      %d  (воскреснут в 00:00 МСК)" % len(влимите))
print("битых (401/403):        %d" % (len(ключи) - len(живые) - len(влимите)))
print("записано в %s: %d ключей" % (ЖИВЫЕ, len(годные)))
print("суточная ёмкость (100 запросов на ключ): ≈ %d запросов = ≈ %d компаний"
      % (len(годные) * 100, len(годные) * 100 * 100))
print("проверка заняла %.0f с" % (time.time() - т0))
