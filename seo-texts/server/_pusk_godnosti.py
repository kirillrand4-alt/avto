# -*- coding: utf-8 -*-
"""Запустить прогон годности отдельным процессом — переживёт таймаут раннера."""
import json
import os
import subprocess
import sys
import time

D = r'C:\sender\server'
p = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'],
                   capture_output=True, text=True)
# Старый прогон (без записи на диск) убиваем: он всё равно потеряет результат.
# Себя из списка исключаем по PID: имя ЭТОГО файла тоже содержит «godnost», и
# первая версия честно убивала сама себя — rc=1 без единой строки в логе.
свой = str(os.getpid())
уже = [l for l in p.stdout.splitlines()
       if 'godnost.py' in l and l.split()[-1] != свой]
out = {'убито_старых': 0}
for l in уже:
    if '--progon' in l:
        continue
    subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, text=True)
    out['убито_старых'] += 1
идёт = [l for l in уже if '--progon' in l]
out['уже_идёт_новый'] = bool(идёт)
if not идёт:
    f = open(os.path.join(D, 'godnost.out'), 'ab')
    pr = subprocess.Popen([sys.executable, os.path.join(D, 'godnost.py'), '--progon'],
                          cwd=D, stdout=f, stderr=subprocess.STDOUT,
                          creationflags=0x00000008 | 0x00000200)
    out['pid'] = pr.pid
    time.sleep(20)
ф = os.path.join(D, 'godnost.jsonl')
out['вердиктов_записано'] = (sum(1 for _ in open(ф, encoding='utf-8', errors='replace'))
                             if os.path.exists(ф) else 0)
print(json.dumps(out, ensure_ascii=False))
