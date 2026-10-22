# -*- coding: utf-8 -*-
"""Куда служба SenderPanel пишет stdout/stderr (только значения AppStdout/
AppStderr из реестра nssm, окружение НЕ читаем) и хвост лога по регулярке.
    log_sluzhby.py <регулярка> [строк=40]"""
import io
import os
import re
import sys
import winreg
from collections import deque

к = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\SenderPanel\Parameters")
пути = []
for имя in ("AppStdout", "AppStderr"):
    try:
        пути.append(winreg.QueryValueEx(к, имя)[0])
    except OSError:
        pass
print("логи службы:", пути)
р = re.compile(sys.argv[1], re.I) if len(sys.argv) > 1 else None
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40
for п in dict.fromkeys(пути):
    if not п or not os.path.exists(п):
        continue
    print("\n== %s (%d КБ)" % (п, os.path.getsize(п) // 1024))
    хв = deque(io.open(п, encoding="utf-8", errors="replace"), maxlen=60000)
    нах = [s.rstrip() for s in хв if (р.search(s) if р else True)]
    for s in нах[-N:]:
        print("  ", s[:260])
