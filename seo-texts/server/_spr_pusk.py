# -*- coding: utf-8 -*-
"""Пуск съёма каталогов отвязанными процессами (раннер режет по 30 минут)."""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8')
ФЛАГИ = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
СКР = r'C:\sender\_tmp\_spr_kat.py'
res = {}
ФАЗЫ = sys.argv[1].split(',') if len(sys.argv) > 1 else ('ozav', 'apk')
for фаза in ФАЗЫ:
    лог = r'C:\sender\_tmp\spr_%s.log' % фаза
    ф = open(лог, 'a', encoding='utf-8')
    p = subprocess.Popen([sys.executable, СКР, фаза], stdout=ф,
                         stderr=subprocess.STDOUT, cwd=r'C:\sender\_tmp',
                         creationflags=ФЛАГИ)
    res[фаза] = {'pid': p.pid, 'лог': лог}
print(json.dumps({'пуск': res, 'скрипт_есть': os.path.exists(СКР)}, ensure_ascii=False))
