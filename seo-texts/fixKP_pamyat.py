# -*- coding: utf-8 -*-
r"""fixKP (22.10): кто занимает оперативную память сервера – и нет ли среди них процессов сессии 3S (скрипты 3s_fix*,
проверки --proverka / --vnutri). Только чтение; данные – PowerShell (Get-CimInstance Win32_Process) в JSON, командные
строки урезаются, секреты не печатаются.

    python3 zapusk_na_servere.py fixKP_pamyat.py
"""
import json
import os
import re
import subprocess

SEKRET = re.compile(r'((?:pass|secret|token|key|parol)\w*)\s*[=:]\s*\S+', re.I)
PS = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,WorkingSetSize,PrivatePageCount,"
      "CreationDate,CommandLine | ConvertTo-Json -Compress -Depth 2")
r = subprocess.run(['powershell', '-NoProfile', '-Command', PS], capture_output=True, timeout=180)
pr = json.loads(r.stdout.decode('utf-8', 'replace') or '[]')
os_ = json.loads(subprocess.run(['powershell', '-NoProfile', '-Command',
                                 'Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json'],
                                capture_output=True, timeout=60).stdout.decode('utf-8', 'replace'))
vsego, svob = os_['TotalVisibleMemorySize'] / 2**20, os_['FreePhysicalMemory'] / 2**20
print('память: всего %.1f ГБ, свободно %.1f ГБ, занято %.1f ГБ' % (vsego, svob, vsego - svob))
gb = lambda x: (x.get('PrivatePageCount') or 0) / 2**30
ws = lambda x: (x.get('WorkingSetSize') or 0) / 2**30
print('сумма по процессам: рабочие наборы %.1f ГБ, личная память %.1f ГБ' % (sum(ws(x) for x in pr), sum(gb(x) for x in pr)))
moi = [x for x in pr if re.search(r'3s_fix|--proverka|--vnutri|_stage\\fix', x.get('CommandLine') or '', re.I)]
print('\nпроцессы сессии 3S: %d' % len(moi))
for x in moi:
    print('   pid %s %.2f ГБ: %s' % (x['ProcessId'], gb(x), SEKRET.sub(r'\1=<скрыто>', x['CommandLine'] or '')[:200]))
gr = {}
for x in pr:
    cmd = x.get('CommandLine') or ''
    if 'headless' in cmd or 'ms-playwright' in cmd:
        k = 'chrome-headless (playwright)'
    elif (x.get('Name') or '').lower() == 'python.exe':
        m = re.search(r'([\w.-]+\.py)\b|-m\s+([\w.]+)', cmd)
        k = 'python: ' + ((m.group(1) or m.group(2)) if m else '?')
    else:
        k = x.get('Name') or '?'
    g = gr.setdefault(k, [0, 0.0, 0.0])
    g[0] += 1
    g[1] += gb(x)
    g[2] += ws(x)
print('\nгруппы (личная память / рабочий набор), топ:')
for k, (n, a, b) in sorted(gr.items(), key=lambda z: -z[1][1])[:22]:
    print('   %-46s процессов %3d   %5.2f ГБ / %5.2f ГБ' % (k[:46], n, a, b))
# кто родитель у headless-хромов
hl = [x for x in pr if 'headless' in (x.get('CommandLine') or '')]
if hl:
    po_pid = {x['ProcessId']: x for x in pr}
    roditeli = {}
    for x in hl:
        p = po_pid.get(x['ParentProcessId'])
        while p and 'headless' in (p.get('CommandLine') or ''):
            p = po_pid.get(p['ParentProcessId'])
        kl = (p['ProcessId'], SEKRET.sub(r'\1=<скрыто>', (p.get('CommandLine') or p.get('Name') or ''))[:180]) if p else ('?', 'родителя нет')
        roditeli[kl] = roditeli.get(kl, 0) + 1
    print('\nheadless-хромы по родителям:')
    for (pid, cmd), n in sorted(roditeli.items(), key=lambda z: -z[1])[:8]:
        print('   %3d шт. ← pid %s: %s' % (n, pid, cmd))
