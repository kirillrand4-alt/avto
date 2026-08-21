# -*- coding: utf-8 -*-
r"""Обёртка: собрать фронт и выложить (раннер не передаёт аргументы сам)."""
import json
import subprocess
import sys

p = subprocess.run([sys.executable, r'C:\sender\server\sobrat_front.py', '--vylozhit'],
                   capture_output=True, text=True, timeout=1500,
                   cwd=r'C:\sender\server')
вывод = ((p.stdout or '') + (p.stderr or '')).strip()
print(json.dumps({'rc': p.returncode, 'хвост': вывод[-2200:]},
                 ensure_ascii=False, indent=1))
