# -*- coding: utf-8 -*-
# 23.10: лаунчер klienty_obhod.py на сервере — N частей (шардов) по T потоков, каждая отдельным отсоединённым процессом.
# Параметры — в KLIENTY_PUSK.json рядом (или по умолчанию ниже): {"N": 12, "T": 96, "src": "...", "limit": 0}.
# Повторный запуск продолжает: пройденные домены каждой части — в klienty-sK-done.txt. Прогресс — дроп klienty-sK-progress.json.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
п = {'N': 12, 'T': 96, 'src': r'C:\sender\_tmp\domains\delegated.txt', 'limit': 0}
ф = os.path.join(DIR, 'KLIENTY_PUSK.json')
if os.path.exists(ф):
    п.update(json.load(open(ф, encoding='utf-8')))
os.makedirs(os.path.join(DIR, 'klienty'), exist_ok=True)
pids = []
for k in range(п['N']):
    лог = os.path.join(DIR, 'klienty', 'klienty-s%d-%s.log' % (k, time.strftime('%d%m-%H%M')))
    арг = [sys.executable, '-u', os.path.join(DIR, 'klienty_obhod.py'), str(k), str(п['N']), str(п['T']), п['src']]
    if п.get('limit'):
        арг.append('--limit=%d' % п['limit'])
    with open(лог, 'wb') as в:
        pr = subprocess.Popen(арг, cwd=DIR, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                              close_fds=False)
    pids.append(pr.pid)
print('===ИТОГ===', json.dumps({'параметры': п, 'pid': pids}, ensure_ascii=False))
