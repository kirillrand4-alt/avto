# -*- coding: utf-8 -*-
"""Запустить dopisat_kc1.py отсоединённым процессом (без лимита раннера в 900 с).
Лог — _ops/dopisat-kc1.log."""
import io
import subprocess
import sys
import time
лог = io.open(r"C:\sender\_ops\dopisat-kc1.log", "a", encoding="utf-8")
п = subprocess.Popen([sys.executable, r"C:\sender\server\ops\dopisat_kc1.py", "2000", "--katit"], cwd=r"C:\sender",
                     stdout=лог, stderr=лог, creationflags=0x00000008 | 0x00000200)
io.open(r"C:\sender\_ops\dopisat-kc1.pid", "w").write(str(п.pid))
time.sleep(10)
print("pid %d жив: %s" % (п.pid, п.poll() is None))
