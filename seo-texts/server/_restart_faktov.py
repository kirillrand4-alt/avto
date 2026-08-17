# -*- coding: utf-8 -*-
"""Перезапустить цикл фактов, чтобы он подхватил остывание молчащей модели."""
import json, os, subprocess, sys, time
D = r'C:\sender\server'
out = {}
p = subprocess.run(['wmic', 'process', 'where', "name='python.exe'", 'get', 'ProcessId,CommandLine'],
                   capture_output=True, text=True)
for l in [x for x in p.stdout.splitlines() if 'fakty_cikl' in x]:
    subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, text=True)
    out.setdefault('убит', []).append(l.split()[-1])
time.sleep(2)
f = open(os.path.join(D, 'fakty_cikl.log'), 'ab')
env = dict(os.environ, FAKTY_PACHKA='60', FAKTY_POTOKOV='12')
pr = subprocess.Popen([sys.executable, os.path.join(D, 'fakty_cikl.py')], cwd=D,
                      stdout=f, stderr=subprocess.STDOUT, env=env,
                      creationflags=0x00000008 | 0x00000200)
out['новый_pid'] = pr.pid
print(json.dumps(out, ensure_ascii=False))
