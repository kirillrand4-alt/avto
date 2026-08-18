# -*- coding: utf-8 -*-
"""Запустить дожим отвязанным процессом (раннер режет задания по 30 минут)."""
import json
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ЛОГ = r'C:\sender\server\probe-dozhim.log'
ф = open(ЛОГ, 'a', encoding='utf-8')
p = subprocess.Popen([sys.executable, r'C:\sender\server\probe_dozhim.py',
                      'Партия 935', '4'],
                     stdout=ф, stderr=subprocess.STDOUT, cwd=r'C:\sender\server',
                     creationflags=(subprocess.DETACHED_PROCESS
                                    | subprocess.CREATE_NEW_PROCESS_GROUP))
print(json.dumps({'pid': p.pid, 'лог': ЛОГ}, ensure_ascii=False))
