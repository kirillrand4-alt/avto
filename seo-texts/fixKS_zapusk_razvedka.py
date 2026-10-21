# -*- coding: utf-8 -*-
r"""fixKS (21.10): как запущены 8011/8012/8014 – цепочка родителей, службы, автозагрузка, файлы с «8014»/«8012».
Только чтение; строки с секретами скрываются.

    python3 zapusk_na_servere.py fixKS_zapusk_razvedka.py
"""
import glob
import io
import os
import re
import subprocess

SEKRET = re.compile(r'(PASS|SECRET|TOKEN|KEY|PAROL|AUTH|BASIC|OBZVON_USERS)', re.I)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, timeout=120).stdout.decode('cp866', 'replace')


def info(pid):
    o = sh('wmic process where processid=%s get CommandLine,ParentProcessId,Name,CreationDate /format:list' % pid)
    return {k.strip(): v.strip() for k, v in (x.split('=', 1) for x in o.split('\r\n') if '=' in x)}


pids = {}
for l in sh('netstat -ano').splitlines():
    if 'LISTENING' in l.upper():
        for port in (8011, 8012, 8014):
            if (':%d ' % port) in l:
                pids[port] = l.split()[-1]
for port, pid in sorted(pids.items()):
    print('\n:%d' % port)
    p = pid
    for _ in range(6):
        d = info(p)
        if not d:
            print('   %s: нет (завершён)' % p)
            break
        print('   %s %s %s: %s' % (p, d.get('Name'), d.get('CreationDate', '')[:14], d.get('CommandLine', '')[:200]))
        p = d.get('ParentProcessId')
        if not p or p == '0':
            break

print('\nслужбы:')
o = sh('wmic service get Name,PathName,State,StartMode /format:list')
for blok in o.split('\r\r\n\r\r\n'):
    if re.search(r'seostat|uvicorn|nssm|obzvon|python', blok, re.I):
        print('  ', ' | '.join(x.strip() for x in blok.split('\r\r\n') if x.strip())[:300])

for put in [r'C:\seostat\drop\run_drop.bat'] + glob.glob(r'C:\ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\*'):
    if os.path.isfile(put):
        t = io.open(put, encoding='utf-8', errors='replace').read()
        t = '\n'.join(('<скрыто>' if SEKRET.search(l) else l) for l in t.splitlines())
        print('\n--- %s\n%s' % (put, t[:1500]))

print('\nфайлы с 8014 / p25 запуском:')
kand = []
for pat in (r'C:\seostat\*.*', r'C:\seostat\drop\*.*', r'C:\seostat\scripts\*.*', r'C:\seostat\deploy\*.*', r'C:\*.bat', r'C:\*.ps1',
            r'C:\sender\*.py', r'C:\sender\*.bat', r'C:\p25\*.*'):
    kand += glob.glob(pat)
for put in kand:
    if not os.path.isfile(put) or os.path.getsize(put) > 2 * 2**20 or put.lower().endswith(('.db', '.gz', '.zip', '.log', '.jsonl', '.json', '.xlsx', '.csv')):
        continue
    try:
        t = io.open(put, encoding='utf-8', errors='replace').read()
    except OSError:
        continue
    if '8014' in t or ('8012' in t and 'uvicorn' in t):
        stroki = [l.strip() for l in t.splitlines() if ('8014' in l or '8012' in l or 'OBZVON_ROOT' in l or '_DB' in l) and not SEKRET.search(l)]
        print('   %s (%s): %s' % (put, os.path.getmtime(put), stroki[:8]))
for d in glob.glob(r'C:\sender\_ops\3s_*'):
    try:
        t = io.open(d, encoding='utf-8', errors='replace').read()
    except OSError:
        continue
    if '8014' in t and ('Popen' in t or 'schtasks' in t):
        print('   ops: %s' % os.path.basename(d))
