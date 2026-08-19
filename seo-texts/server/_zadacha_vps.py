# -*- coding: utf-8 -*-
"""Отправить подписанное задание раннеру VPS и дождаться ответа."""
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
env = {}
for l in open(r'C:\sender\server\runner-secrets.env', encoding='utf-8'):
    if '=' in l and not l.strip().startswith('#'):
        k, v = l.split('=', 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
url, tok, секрет = env['DROP_URL'].rstrip('/'), env['DROP_TOKEN'], env.get('JOB_SECRET', '')


def дроп(метод, имя, данные=None):
    к = ['curl', '-s', '-H', 'X-Drop-Token: ' + tok]
    if метод == 'PUT':
        к += ['-X', 'PUT', '--data-binary', '@-', '%s/%s' % (url, имя)]
        return subprocess.run(к, input=данные, capture_output=True, text=True,
                              timeout=180).stdout
    к += ['%s/%s' % (url, имя)]
    return subprocess.run(к, capture_output=True, text=True, timeout=180).stdout


задача = sys.argv[1] if len(sys.argv) > 1 else 'ping'
аргументы = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
jid = '%d-%d-%s' % (int(time.time()), os.getpid(), os.urandom(3).hex())
задание = {'id': jid, 'task': задача, 'args': аргументы, 'ts': int(time.time())}
канон = json.dumps({k: задание[k] for k in ('id', 'task', 'args', 'ts')},
                   sort_keys=True, separators=(',', ':'), ensure_ascii=False)
if секрет:
    задание['sig'] = hmac.new(секрет.encode(), канон.encode(), hashlib.sha256).hexdigest()
дроп('PUT', 'vjob-%s.json' % jid, json.dumps(задание, ensure_ascii=False))
ответ = None
for _ in range(40):
    time.sleep(6)
    r = дроп('GET', 'vresult-%s.json' % jid)
    if r and r.strip().startswith('{'):
        try:
            ответ = json.loads(r)
            break
        except Exception:  # noqa: BLE001
            pass
print(json.dumps({'id': jid, 'задача': задача, 'ответ': ответ or 'раннер не ответил за 4 минуты'},
                 ensure_ascii=False, indent=1)[:3000])
