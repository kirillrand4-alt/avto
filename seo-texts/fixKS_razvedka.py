# -*- coding: utf-8 -*-
r"""fixKS (21.10): разведка перед переносом статистики Meyer в панель КЦ. Только чтение.

Процессы на 8011/8012/8014/8016 (командные строки, родитель), задачи планировщика про seostat/obzvon,
.bat-запускатели, ключи путей в .env (без секретов), замок. Код обеих панелей (*.py, шаблоны, css/js без
каталога скриншотов) – архивом на дроп `fixKS-kod.tar.gz` для чтения на месте.

    python3 zapusk_na_servere.py fixKS_razvedka.py
"""
import csv
import glob
import io
import os
import re
import subprocess
import tarfile

DROP = r'C:\seostat\drop\drop-storage'
SEKRET = re.compile(r'(PASS|SECRET|TOKEN|KEY|PAROL|AUTH|BASIC)', re.I)


def sh(cmd, kod='cp866'):
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=120)
    return r.stdout.decode(kod, 'replace')


# --- процессы
pid_port = {}
for l in sh('netstat -ano').splitlines():
    if 'LISTENING' in l.upper():
        for port in (8011, 8012, 8014, 8016):
            if (':%d ' % port) in l:
                pid_port[l.split()[-1]] = port
print('слушают:', pid_port)
for pid, port in sorted(pid_port.items(), key=lambda x: x[1]):
    o = sh('wmic process where processid=%s get CommandLine,ParentProcessId,CreationDate /format:list' % pid)
    d = dict(x.split('=', 1) for x in o.split('\r\n') if '=' in x)
    d = {k.strip(): v.strip() for k, v in d.items()}
    pp = d.get('ParentProcessId', '')
    o2 = sh('wmic process where processid=%s get CommandLine,Name /format:list' % pp) if pp else ''
    d2 = {k.strip(): v.strip() for k, v in (x.split('=', 1) for x in o2.split('\r\n') if '=' in x)}
    print('\n:%d pid %s создан %s\n   cmd: %s\n   родитель %s: %s' % (
        port, pid, d.get('CreationDate', '')[:14], d.get('CommandLine', '')[:300], pp, d2.get('CommandLine', d2.get('Name', ''))[:300]))
    # дети uvicorn --reload / дедушка
    o3 = sh('wmic process where parentprocessid=%s get ProcessId,CommandLine /format:list' % pid)
    deti = [x.strip() for x in o3.split('\r\n') if x.startswith('CommandLine=')]
    if deti:
        print('   дети:', [x[12:200] for x in deti])

# --- планировщик
o = sh('schtasks /query /fo csv /v')
rows = list(csv.reader(io.StringIO(o)))
if rows:
    head = rows[0]
    print('\nпланировщик, колонки:', len(head))
    vidno = set()
    for r in rows[1:]:
        s = ' '.join(r)
        if re.search(r'seostat|obzvon|uvicorn|centro|p25', s, re.I):
            klyuch = (r[1] if len(r) > 1 else '')
            if klyuch in vidno:
                continue
            vidno.add(klyuch)
            pole = dict(zip(head, r))
            vyb = {k: v for k, v in pole.items() if re.search(r'TaskName|Имя задачи|Task To Run|Задача|Start In|Рабочая|Status|Состояние|Last Run|Последний|Schedule Type|Тип расписания|Run As|Запуск от', k, re.I)}
            print('  ', {k: v[:220] for k, v in vyb.items()})

# --- .bat и запускатели
for put in glob.glob(r'C:\seostat\*.bat') + glob.glob(r'C:\seostat\*.cmd') + glob.glob(r'C:\seostat\zapusk*.py') + glob.glob(r'C:\seostat\start*.py'):
    t = io.open(put, encoding='utf-8', errors='replace').read()
    t = '\n'.join(('<скрыто>' if SEKRET.search(l) else l) for l in t.splitlines())
    print('\n--- %s (%d байт)\n%s' % (put, os.path.getsize(put), t[:700]))

# --- .env: только ключи путей
for env in () if '--bez-arhiva' in __import__('sys').argv else (r'C:\seostat\.env', r'C:\centro2\.env'):
    if os.path.exists(env):
        print('\n%s:' % env)
        for l in io.open(env, encoding='utf-8', errors='replace'):
            if '=' not in l or l.lstrip().startswith('#'):
                continue
            k, v = l.split('=', 1)
            k = k.strip()
            if SEKRET.search(k):
                print('   %s=<скрыто>' % k)
            elif re.search(r'DB|PATH|ROOT|DIR|PORT|URL', k, re.I):
                print('   %s=%s' % (k, v.strip()[:160]))
            else:
                print('   %s=…' % k)
print('\nзамок seostat:', os.path.exists(r'C:\seostat\_zamok.txt'), ' замок centro2:', os.path.exists(r'C:\centro2\_zamok.txt'))
print('C:\\seostat\\_bekap есть:', os.path.isdir(r'C:\seostat\_bekap'))
for p in glob.glob(r'C:\seostat\data\*.db'):
    print('   база %s %.1f МБ' % (p, os.path.getsize(p) / 2**20))

# --- архив кода
import sys
if '--bez-arhiva' in sys.argv:
    raise SystemExit(0)
ark = os.path.join(DROP, 'fixKS-kod.tar.gz')
n = 0
with tarfile.open(ark, 'w:gz') as tf:
    for koren, metka in ((r'C:\seostat', 'seostat'), (r'C:\centro2', 'centro2')):
        app = os.path.join(koren, 'app')
        for dp, dn, fn in os.walk(app):
            dn[:] = [d for d in dn if d not in ('__pycache__', 'dokaz', 'node_modules') and not os.path.islink(os.path.join(dp, d))]
            for f in fn:
                if not f.endswith(('.py', '.html', '.css', '.js', '.txt', '.json')):
                    continue
                p = os.path.join(dp, f)
                if os.path.getsize(p) > 3 * 2**20:
                    continue
                tf.add(p, arcname=metka + '/' + os.path.relpath(p, koren).replace('\\', '/'))
                n += 1
        for f in ('zapusk.py',):
            p = os.path.join(koren, f)
            if os.path.exists(p):
                tf.add(p, arcname=metka + '/' + f)
print('\nархив: %s, файлов %d, %.1f МБ' % (ark, n, os.path.getsize(ark) / 2**20))
