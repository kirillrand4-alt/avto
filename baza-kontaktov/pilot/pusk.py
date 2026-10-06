# -*- coding: utf-8 -*-
"""Запустить sbor_serp.py (или analiz.py) отдельным процессом — переживает таймаут задания.
    pusk.py serp <pages>   |   pusk.py analiz proverka   |   pusk.py status"""
import json, os, subprocess, sys, time
D = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
o = {}
if sys.argv[1] == 'serp':
    cmd = [PY, '-u', os.path.join(D, 'sbor_serp.py'), '--pages', sys.argv[2]] + sys.argv[3:]
elif sys.argv[1] == 'kat':
    cmd = [PY, '-u', os.path.join(D, 'katalogi.py')] + sys.argv[2:]
elif sys.argv[1] == 'analiz':
    cmd = [PY, '-u', os.path.join(D, 'analiz.py')] + sys.argv[2:]
elif sys.argv[1] == 'stop':
    cmd = None
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | ? { $_.CommandLine -like '*baza_pilot*sbor_serp*' } | "
                        "% { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                       capture_output=True, text=True, timeout=120)
    o['stopped'] = r.stdout.split()
else:
    cmd = None
if cmd:
    log = open(os.path.join(D, 'pusk-%s-%s.log' % (sys.argv[1], time.strftime('%H%M'))), 'wb')
    p = subprocess.Popen(cmd, cwd=D, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT, close_fds=True)  # иначе задание раннера ждёт дочерний процесс
    o['pid'] = p.pid
    time.sleep(60)
for f in ('BAZA-PILOT-SERP.jsonl', 'sayty.jsonl', 'IDEI-SERP.jsonl', 'GLUBINA-SERP.jsonl', 'MASSA-SERP.jsonl', 'KATALOGI.jsonl'):
    fp = os.path.join(D, f)
    if os.path.exists(fp):
        L = open(fp, encoding='utf-8').readlines()
        o[f] = len(L)
        if f.endswith('SERP.jsonl') and f != 'BAZA-PILOT-SERP.jsonl':
            js = [json.loads(x) for x in L]
            o['errors'] = sum(1 for j in js if j.get('error'))
            o['docs'] = sum(len(j['docs']) for j in js)
            o['last_err'] = [j['error'][:60] for j in js if j.get('error')][-3:]
logs = sorted((x for x in os.listdir(D) if x.startswith('pusk-')), key=lambda x: os.path.getmtime(os.path.join(D, x)))
if logs:
    o['log'] = logs[-1]
    o['tail'] = open(os.path.join(D, logs[-1]), encoding='utf-8', errors='replace').read()[-600:]
r = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | ? { $_.CommandLine -like '*baza_pilot*' -and $_.CommandLine -notlike '*pusk.py*' } | "
                    "% { '' + $_.ProcessId + ' ' + $_.CreationDate.ToString('HH:mm') + ' ' + $_.CommandLine.Substring([Math]::Max(0,$_.CommandLine.Length-60)) }"],
                   capture_output=True, text=True, timeout=120)
o['procs'] = r.stdout.strip().splitlines()
o['now'] = time.strftime('%H:%M:%S')
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
