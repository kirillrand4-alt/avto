# -*- coding: utf-8 -*-
r"""fixSL (21.10): снимок потоков зависшей панели Meyer (py-spy dump, только чтение процесса) и затем перезапуск через
задачу автозапуска. py-spy ставится во временную папку C:\centro2\_tools (pip --target), систему не меняет.

    python3 zapusk_na_servere.py fixSL_stek.py [--perezapusk]
"""
import io
import os
import re
import subprocess
import sys
import time
import urllib.request

TOOLS = r'C:\centro2\_tools'


def pid_na(port):
    o = subprocess.run('netstat -ano -p tcp', shell=True, capture_output=True, text=True).stdout
    return next((l.split()[-1] for l in o.splitlines() if (':%d ' % port) in l and 'LISTEN' in l.upper()), None)


pid = pid_na(8016)
print('PID 8016:', pid)
spy = os.path.join(TOOLS, 'bin', 'py-spy.exe')
if not os.path.exists(spy):
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--target', TOOLS, 'py-spy'], capture_output=True, text=True)
    print('pip py-spy:', r.returncode, r.stderr[-300:])
if not os.path.exists(spy):
    spy = next((os.path.join(k, f) for k, _, fs in os.walk(TOOLS) for f in fs if f.lower() == 'py-spy.exe'), spy)
if pid and os.path.exists(spy):
    r = subprocess.run([spy, 'dump', '--pid', pid], capture_output=True, text=True, errors='replace', timeout=120)
    t = r.stdout + r.stderr
    io.open(r'C:\seostat\drop\drop-storage\fixSL-stek-%s.txt' % time.strftime('%Y%m%d-%H%M%S'), 'w', encoding='utf-8').write(t)
    potoki = t.split('Thread ')
    print('потоков:', len(potoki) - 1)
    sch = {}
    for p in potoki[1:]:
        verh = [s.strip() for s in p.splitlines()[1:4] if s.strip()]
        kl = ' | '.join(verh)[:220]
        sch[kl] = sch.get(kl, 0) + 1
    for kl, n in sorted(sch.items(), key=lambda x: -x[1])[:12]:
        print('%3d × %s' % (n, kl))
else:
    print('py-spy недоступен')
if '--perezapusk' in sys.argv and pid:
    subprocess.run('taskkill /PID %s /F /T' % pid, shell=True, capture_output=True)
    time.sleep(3)
    subprocess.run('schtasks /run /tn "\\centro2-meyer"', shell=True, capture_output=True)
    for _ in range(20):
        time.sleep(3)
        if pid_na(8016):
            break
    time.sleep(6)
    for u in ('/obzvon-meyer/centro/login', '/obzvon-meyer/static/css/centro.css'):
        t0 = time.time()
        try:
            k = urllib.request.urlopen('http://127.0.0.1:8016' + u, timeout=60).status
        except Exception as e:  # noqa: BLE001
            k = repr(e)[:60]
        print('после перезапуска %s: %s за %.1f с' % (u, k, time.time() - t0))
