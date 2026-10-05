# -*- coding: utf-8 -*-
"""Запустить sbor_serp.py (или analiz.py) отдельным процессом — переживает таймаут задания.
    pusk.py serp <pages>   |   pusk.py analiz proverka   |   pusk.py status"""
import json, os, subprocess, sys, time
D = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
o = {}
if sys.argv[1] == 'serp':
    cmd = [PY, '-u', os.path.join(D, 'sbor_serp.py'), '--pages', sys.argv[2]]
elif sys.argv[1] == 'analiz':
    cmd = [PY, '-u', os.path.join(D, 'analiz.py')] + sys.argv[2:]
else:
    cmd = None
if cmd:
    log = open(os.path.join(D, 'pusk-%s-%s.log' % (sys.argv[1], time.strftime('%H%M'))), 'wb')
    p = subprocess.Popen(cmd, cwd=D, creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT, close_fds=False)
    o['pid'] = p.pid
    time.sleep(60)
for f in ('BAZA-PILOT-SERP.jsonl', 'sayty.jsonl'):
    fp = os.path.join(D, f)
    if os.path.exists(fp):
        L = open(fp, encoding='utf-8').readlines()
        o[f] = len(L)
        if f.startswith('BAZA'):
            js = [json.loads(x) for x in L]
            o['errors'] = sum(1 for j in js if j.get('error'))
            o['docs'] = sum(len(j['docs']) for j in js)
            o['last_err'] = [j['error'][:60] for j in js if j.get('error')][-3:]
logs = sorted(x for x in os.listdir(D) if x.startswith('pusk-'))
if logs:
    o['log'] = logs[-1]
    o['tail'] = open(os.path.join(D, logs[-1]), encoding='utf-8', errors='replace').read()[-600:]
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
