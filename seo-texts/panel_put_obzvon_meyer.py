# -*- coding: utf-8 -*-
"""Перенос копии на путь /obzvon-meyer: только .env копии, кода не касаюсь.

ПОЧЕМУ ИМЕННО ТАК. В config.py префикс считается из поля obzvon_root_path, то есть из
переменной OBZVON_ROOT_PATH. Значит перенос — одна строка, а не правка 90 ссылок в
шаблонах. Строк «/centro» в копии 103, но все они пишутся как «{{ base_path }}/centro»
или «BP + "/centro"», поэтому меняется префикс — и уезжают все сразу.

ПОЧЕМУ НЕ /obzvon/meyer. Замер: на боевой панели /obzvon/meyer и /obzvon/kc отвечают 401
обзвонной авторизации, то есть путь занят СТАРЫМ обзвоном (callbase.BASES = kc, meyer).
Поставить копию туда значило бы затенить работающую страницу.

ЛОВУШКА, КОТОРУЮ ЗДЕСЬ ПРОВЕРЯЮ. pydantic-settings берёт переменную из окружения
ПРОЦЕССА раньше, чем из .env. Если OBZVON_ROOT_PATH задана глобально на сервере, правка
.env окажется бесполезной и путь молча останется прежним. Поэтому значение проверяется
в рабочем процессе, а не по файлу.
"""
import io
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

KOREN = r'C:\centro2'
ENV = os.path.join(KOREN, '.env')
VENV = r'C:\seostat\.venv\Scripts\python.exe'
PORT = 8016
NOVYY_PUT = '/obzvon-meyer'
LOG = os.path.join(KOREN, 'centro2.log')

itog = []


def skazat(s):
    itog.append(str(s))
    print(s)


# ---------------------------------------------------------------- 0. что сейчас в env
glob = os.environ.get('OBZVON_ROOT_PATH')
skazat('OBZVON_ROOT_PATH в окружении раннера: %s'
       % (repr(glob) if glob is not None else 'не задана'))

stroki = io.open(ENV, encoding='utf-8', errors='replace').read().splitlines()
bylo = [l for l in stroki if re.match(r'^\s*OBZVON_ROOT_PATH\s*=', l, re.I)]
skazat('строк OBZVON_ROOT_PATH в .env копии: %d%s'
       % (len(bylo), (' (%s)' % bylo[0].strip()) if bylo else ''))

# ---------------------------------------------------------------- 1. правка .env
novye = []
zamen = 0
for l in stroki:
    if re.match(r'^\s*OBZVON_ROOT_PATH\s*=', l, re.I):
        if zamen == 0:
            novye.append('OBZVON_ROOT_PATH=%s' % NOVYY_PUT)
            zamen += 1
        continue
    novye.append(l)
if zamen == 0:
    novye.append('')
    novye.append('# --- свой путь копии: боевой обзвон остаётся на /obzvon,'
                 ' старые базы kc и meyer тоже')
    novye.append('OBZVON_ROOT_PATH=%s' % NOVYY_PUT)
    zamen = 1
io.open(ENV, 'w', encoding='utf-8').write('\n'.join(novye) + '\n')
skazat('.env копии: OBZVON_ROOT_PATH=%s (правок %d)' % (NOVYY_PUT, zamen))

# боевой .env не трогаю — печатаю его отпечаток, чтобы это было видно, а не на слово
boevoy = r'C:\seostat\.env'
skazat('боевой .env: %d байт, изменён %s (не трогала)'
       % (os.path.getsize(boevoy),
          time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(boevoy)))))


# ---------------------------------------------------------------- 2. перезапуск
def pid_na_portu(port):
    r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    return {l.split()[-1] for l in r.stdout.decode('cp866', 'replace').splitlines()
            if (':%d ' % port) in l and 'LISTENING' in l.upper()}


for p in pid_na_portu(PORT):
    subprocess.run(['taskkill', '/PID', p, '/F'], capture_output=True, timeout=60)
time.sleep(2)
log = io.open(LOG, 'a', encoding='utf-8', errors='replace')
log.write('\n===== перезапуск на %s: %s =====\n'
          % (NOVYY_PUT, time.strftime('%Y-%m-%d %H:%M:%S')))
log.flush()
# Переменную передаю и в окружении процесса тоже: так она перебьёт возможное глобальное
# значение, а не окажется под ним.
sreda = dict(os.environ, PYTHONIOENCODING='utf-8', ENV_FILE=ENV,
             OBZVON_ROOT_PATH=NOVYY_PUT)
subprocess.Popen(
    [VENV, '-m', 'uvicorn', 'app.obzvon:app', '--host', '127.0.0.1', '--port', str(PORT)],
    cwd=KOREN, stdout=log, stderr=subprocess.STDOUT,
    creationflags=0x00000008 | 0x00000200, close_fds=True, env=sreda)
for _ in range(30):
    time.sleep(1)
    if pid_na_portu(PORT):
        break
skazat('порт %d слушает PID %s' % (PORT, ', '.join(sorted(pid_na_portu(PORT))) or 'НИКТО'))


# ---------------------------------------------------------------- 3. проверка путей
class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


op = urllib.request.build_opener(BezRedirekta)


def proba(port, put):
    try:
        o = op.open('http://127.0.0.1:%d%s' % (port, put), timeout=25)
        return o.status, len(o.read()), ''
    except urllib.error.HTTPError as e:
        return e.code, len((e.read() or b'')), (e.headers.get('Location') or '')
    except Exception as e:  # noqa: BLE001
        return 'ОШИБКА', 0, str(e)[:60]


skazat('')
skazat('--- копия на новом пути (8016)')
for put in (NOVYY_PUT + '/centro', NOVYY_PUT + '/centro/login',
            NOVYY_PUT + '/centro/stats', NOVYY_PUT + '/centro/park'):
    kod, dl, kuda = proba(PORT, put)
    skazat('   %-34s -> %-5s %6s байт%s'
           % (put, kod, dl, ('  Location=' + kuda) if kuda else ''))
skazat('--- старый путь на копии должен исчезнуть')
for put in ('/obzvon/centro', '/obzvon/centro/login'):
    kod, dl, kuda = proba(PORT, put)
    skazat('   %-34s -> %-5s %6s байт%s'
           % (put, kod, dl, ('  Location=' + kuda) if kuda else ''))
skazat('--- боевая панель (8012) должна остаться как была')
for put in ('/obzvon/centro', '/obzvon/meyer', '/obzvon/kc'):
    kod, dl, kuda = proba(8012, put)
    skazat('   %-34s -> %-5s %6s байт%s'
           % (put, kod, dl, ('  Location=' + kuda) if kuda else ''))

# ---------------------------------------------------------------- 4. что реально внутри
skazat('')
pr = subprocess.run(
    [VENV, '-c',
     'import os,sys;sys.path.insert(0,r"%s");os.chdir(r"%s");'
     'from dotenv import load_dotenv;load_dotenv(r"%s",override=True);'
     'from app.config import get_settings as g;'
     'print("obzvon_root_path=%%r obzvon_path=%%r" %% '
     '(g().obzvon_root_path, g().obzvon_path))' % (KOREN, KOREN, ENV)],
    capture_output=True, timeout=300, cwd=KOREN,
    env=dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH=NOVYY_PUT))
skazat('настройки копии: %s' % (pr.stdout.decode('utf-8', 'replace').strip()
                                or pr.stderr.decode('utf-8', 'replace')[-200:]))

print('\n===== ИТОГ =====')
for s in itog:
    print(s)
