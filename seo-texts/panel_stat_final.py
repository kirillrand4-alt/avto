# -*- coding: utf-8 -*-
"""Финальная проверка копии: перезапуск, обе роли, отказ продавцу, живой HTTP.

Проверяю не только что админу 200, но и что продавцу 403: страница показывает чужие
очереди и чужие результаты, и если роль не проверяется, это утечка внутрь команды.
"""
import io
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
PORT = 8016
LOG = os.path.join(KOREN, 'centro2.log')

if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:],
                       capture_output=True, timeout=1500,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace'))
    raise SystemExit(r.returncode)

itog = []


def skazat(s):
    itog.append(s)
    print(s)


# ---------- 1. перезапуск, чтобы на порту работал ровно нынешний код
def pid_na_portu(port):
    r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    return {l.split()[-1] for l in r.stdout.decode('cp866', 'replace').splitlines()
            if (':%d ' % port) in l and 'LISTENING' in l.upper()}


for p in pid_na_portu(PORT):
    subprocess.run(['taskkill', '/PID', p, '/F'], capture_output=True, timeout=60)
time.sleep(2)
log = io.open(LOG, 'a', encoding='utf-8', errors='replace')
log.write('\n===== перезапуск %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
log.flush()
subprocess.Popen(
    [VENV, '-m', 'uvicorn', 'app.obzvon:app', '--host', '127.0.0.1', '--port', str(PORT)],
    cwd=KOREN, stdout=log, stderr=subprocess.STDOUT,
    creationflags=0x00000008 | 0x00000200, close_fds=True,
    env=dict(os.environ, PYTHONIOENCODING='utf-8', ENV_FILE=os.path.join(KOREN, '.env')))
for _ in range(30):
    time.sleep(1)
    if pid_na_portu(PORT):
        break
skazat('порт %d слушает PID %s' % (PORT, ', '.join(sorted(pid_na_portu(PORT))) or 'НИКТО'))

# ---------- 2. проверка ролей внутри процесса
os.chdir(KOREN)
sys.path.insert(0, KOREN)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(KOREN, '.env'), override=True)
except Exception:  # noqa: BLE001
    pass
from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

vnesh = create_app()
vnutr = next(z for z in vars(vnesh).values()
             if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))

for rol, imya in (('admin', 'admin'), ('sales', 'user2')):
    vnutr.dependency_overrides[rcs.current_user] = (
        lambda r=rol, i=imya: {'username': i, 'role': r, 'is_active': 1})
    with TestClient(vnutr) as k:
        o1 = k.get('/obzvon/centro/stats')
        o2 = k.get('/obzvon/centro')
        knopka = '/centro/stats' in o2.text
        skazat('роль %-6s (%s): /centro/stats -> %s | главная -> %s,'
               ' кнопка «Статистика» в шапке: %s'
               % (rol, imya, o1.status_code, o2.status_code,
                  'видна' if knopka else 'не видна'))

# ---------- 3. живой HTTP на порту
class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


op = urllib.request.build_opener(BezRedirekta)
for put in ('/obzvon/centro/login', '/obzvon/centro/stats', '/obzvon/centro/stats?user=user1'):
    try:
        o = op.open('http://127.0.0.1:%d%s' % (PORT, put), timeout=30)
        skazat('  живой HTTP %-34s -> %s, %d байт' % (put, o.status, len(o.read())))
    except urllib.error.HTTPError as e:
        skazat('  живой HTTP %-34s -> %s%s' % (put, e.code,
               ', Location=' + (e.headers.get('Location') or '')))
    except Exception as e:  # noqa: BLE001
        skazat('  живой HTTP %-34s -> ОШИБКА %s' % (put, str(e)[:60]))

print('\n===== ИТОГ =====')
for s in itog:
    print(s)
