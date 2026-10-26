# -*- coding: utf-8 -*-
"""Есть ли py-spy на сервере (для снимка стека зависшей службы). Только чтение."""
import shutil
import subprocess
import sys
print("py-spy в PATH:", shutil.which("py-spy"))
r = subprocess.run([sys.executable, "-m", "pip", "show", "py-spy"], capture_output=True, text=True)
print("pip show:", (r.stdout or r.stderr)[:200])
