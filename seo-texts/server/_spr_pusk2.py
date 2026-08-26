# -*- coding: utf-8 -*-
"""Пуск фазы agro (производители+дилеры agrobase) отвязанным процессом."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ФЛАГИ = 0x00000008 | 0x00000200
лог = r'C:\sender\_tmp\spr_agro.log'
ф = open(лог, 'a', encoding='utf-8')
p = subprocess.Popen([sys.executable, r'C:\sender\_tmp\_spr_kat.py', 'agro'],
                     stdout=ф, stderr=subprocess.STDOUT, cwd=r'C:\sender\_tmp',
                     creationflags=ФЛАГИ)
print(json.dumps({'pid': p.pid, 'лог': лог}, ensure_ascii=False))
