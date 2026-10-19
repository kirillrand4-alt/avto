# -*- coding: utf-8 -*-
r"""fixSS (19.10): после перезагрузки панель Meyer (автозапуск SYSTEM) не видит CENTRO_SESSION_SECRET – он был только в
окружении служебного процесса, через который панель перезапускали раньше. Чиним: тот же секрет (из окружения этого
процесса, значение НЕ печатается) дописывается в C:\centro2\.env (zapusk.py грузит .env до импорта приложения),
затем панель перезапускается через задачу автозапуска \centro2-meyer. Старые сеансы остаются действительными.
Плюс только чтение: что с панелью КЦ на :8012 (502).

    python3 zapusk_na_servere.py fixSS_pochinit.py [--primenit]
"""
import io
import os
import re
import shutil
import subprocess
import time
import urllib.request

IMYA = 'CENTRO_SESSION_SECRET'
ENV = r'C:\centro2\.env'


def otvet(url):
    try:
        r = urllib.request.urlopen(url, timeout=15)
        return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001
        return repr(e)[:80]


def pid_na(port):
    o = subprocess.run('netstat -ano -p tcp', shell=True, capture_output=True, text=True).stdout
    return sorted({l.split()[-1] for l in o.splitlines() if (':%d ' % port) in l and 'LISTEN' in l.upper()})


print('8016 /centro без cookie до:', otvet('http://127.0.0.1:8016/obzvon-meyer/centro'))
if '--primenit' in __import__('sys').argv:
    sek = os.environ.get(IMYA, '').strip()
    if len(sek) < 32:
        raise SystemExit('в окружении нет годного секрета – ничего не делаю')
    t = io.open(ENV, encoding='utf-8').read()
    if re.search(r'^\s*%s\s*=' % IMYA, t, re.M):
        print('.env: ключ уже есть – не трогаю')
    else:
        shutil.copy2(ENV, ENV + '.bak-fixSS-' + time.strftime('%Y%m%d-%H%M%S'))
        with io.open(ENV, 'a', encoding='utf-8') as f:
            f.write(('' if t.endswith('\n') else '\n') + '# fixSS 19.10: секрет подписи сеансов панели Meyer (нужен автозапуску)\n'
                    '%s=%s\n' % (IMYA, sek))
        print('.env: ключ дописан (длина %d), копия прежнего .env рядом' % len(sek))
    for p in pid_na(8016):
        subprocess.run('taskkill /PID %s /F /T' % p, shell=True, capture_output=True)
    time.sleep(3)
    print('schtasks /run:', subprocess.run('schtasks /run /tn "\\centro2-meyer"', shell=True, capture_output=True, text=True,
                                           errors='replace').stdout.strip()[:120])
    for _ in range(20):
        time.sleep(3)
        if pid_na(8016):
            break
    time.sleep(5)
    print('8016 PID после:', pid_na(8016))
    print('8016 /login после:', otvet('http://127.0.0.1:8016/obzvon-meyer/centro/login'))
    print('8016 /centro без cookie после (ждём 303/200, не 503):', otvet('http://127.0.0.1:8016/obzvon-meyer/centro'))

# ---- панель КЦ :8012 – только чтение
print('\n8012 слушает:', pid_na(8012) or 'никто')
o = subprocess.run('schtasks /query /fo csv /nh', shell=True, capture_output=True, text=True, errors='replace').stdout
print('задачи планировщика с obzvon/centro/8012:', [l.split(',')[0] for l in o.splitlines() if re.search(r'(?i)obzvon|centro|8012|seostat', l)][:10])
for kand in (r'C:\seostat', r'C:\centro'):
    if os.path.isdir(kand):
        print(kand, [f for f in os.listdir(kand) if re.search(r'(?i)zapusk|start|run|\.bat|\.cmd|\.ps1', f)][:15])
