# -*- coding: utf-8 -*-
"""Запустить копию на 8016 отцеплённым процессом и проверить, что отвечает.

Отцепляю через DETACHED_PROCESS: задание раннера должно завершиться, а сервер остаться.
Если запускать обычным Popen без этого, uvicorn умрёт вместе с заданием.
Проверка — 401 от Basic-авторизации: это значит приложение поднялось и отвечает.
Пароли не подставляю и не печатаю.
"""
import os, subprocess, time, urllib.error, urllib.request

KOREN = r'C:\centro2'
VENV = r'C:\seostat\.venv\Scripts\python.exe'
PORT = 8016

# уже запущено?
r = subprocess.run(['cmd', '/c', 'netstat -ano -p tcp | findstr :%d' % PORT],
                   capture_output=True, timeout=40)
uzhe = r.stdout.decode('cp866', 'replace').strip()
print('порт %d до запуска: %s' % (PORT, uzhe[:120] or 'свободен'))

if 'LISTENING' not in uzhe:
    DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    log = open(os.path.join(KOREN, 'centro2.log'), 'ab')
    subprocess.Popen([VENV, '-m', 'uvicorn', 'app.obzvon:app',
                      '--host', '127.0.0.1', '--port', str(PORT)],
                     cwd=KOREN, stdout=log, stderr=log,
                     creationflags=DETACHED, close_fds=True)
    print('запущено, жду подъёма...')
    time.sleep(12)

for popytka in range(5):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/obzvon/centro/login' % PORT,
                                    timeout=10) as o:
            print('ОТВЕТ: HTTP %s, знаков %d' % (o.status, len(o.read())))
            break
    except urllib.error.HTTPError as e:
        print('ОТВЕТ: HTTP %s — приложение живо (это Basic-авторизация)' % e.code)
        break
    except Exception as e:
        print('  попытка %d: %s' % (popytka + 1, str(e)[:80]))
        time.sleep(5)

r = subprocess.run(['cmd', '/c', 'netstat -ano -p tcp | findstr :%d' % PORT],
                   capture_output=True, timeout=40)
print('порт %d после: %s' % (PORT, r.stdout.decode('cp866', 'replace').strip()[:120]))
p = os.path.join(KOREN, 'centro2.log')
if os.path.exists(p):
    t = open(p, encoding='utf-8', errors='replace').read()
    print('\nхвост лога копии:')
    for l in t.strip().split('\n')[-12:]:
        print('   %s' % l[:112])
