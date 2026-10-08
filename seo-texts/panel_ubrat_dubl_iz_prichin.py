# -*- coding: utf-8 -*-
"""Убрать «дубль» из причин «Компания не понравилась».

Владелец: «убери компания не понравилась — дубль, чтобы не плодить очереди». Для дублей
есть отдельный результат «Дубль — уже работают» со своей вкладкой; причина «дубль» внутри
«не понравилась» давала бы вторую дорогу для того же случая, и дубли расползались бы по
двум очередям.

Список причин — одна константа PRICHINY_NE_PONRAVILAS: из неё строится меню и по ней же
проверяет сервер, поэтому правка в одном месте убирает пункт и там, и там.
"""
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
PORT = 8016
PUT = '/obzvon-meyer'
OSTAYUTSYA = ['неверно указан номер', 'нету ФТС и не надо (для хол)',
              'клиент не выходит на связь (3 звонка/2 письма)', 'уже купили у конкурентов']

if '--proverka' in sys.argv:
    sys.path.insert(0, KOREN)
    import zapusk  # noqa: F401
    import logging
    import warnings
    warnings.filterwarnings('ignore')
    logging.disable(logging.CRITICAL)
    from app.api import routes_centro_sales as rcs
    from app.obzvon import create_app
    from fastapi.testclient import TestClient

    plohih = 0

    def proverit(u, t):
        global plohih
        if not u:
            plohih += 1
        print('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))

    proverit(rcs.PRICHINY_NE_PONRAVILAS == OSTAYUTSYA, 'константа: %s' % rcs.PRICHINY_NE_PONRAVILAS)
    vnutr = next(z for z in vars(create_app()).values()
                 if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': 'meyer_admin', 'role': 'admin', 'is_active': 1}
    vnutr.dependency_overrides[rcs._same_origin] = lambda: None
    s = sqlite3.connect(os.environ['CENTRO_SALES_DB'])
    inn = s.execute("select a.inn from company_assignment a left join company_state st on st.inn=a.inn "
                    "where st.inn is null limit 1").fetchone()[0]
    do = s.execute('select count(*) from company_state').fetchone()[0]
    with TestClient(vnutr) as k:
        t = k.get(PUT + '/centro?inn=' + inn).text
        pod = re.findall(r'data-value="ne_ponravilas" data-prichina="([^"]*)"', t)
        proverit(pod == OSTAYUTSYA, 'в меню карточки причин %d: %s' % (len(pod), pod))
        proverit('Дубль — уже работают' in t, 'отдельный результат «Дубль — уже работают» на месте')
        # 422 возвращается ДО записи — рабочую базу этот запрос не меняет
        o = k.post(PUT + '/centro/save', data={'inn': inn, 'call_result': 'ne_ponravilas',
                                               'prichina': 'дубль', 'return_query': ''},
                   follow_redirects=False)
        proverit(o.status_code == 422, 'причину «дубль» сервер больше не принимает: %s' % o.status_code)
    posle = s.execute('select count(*) from company_state').fetchone()[0]
    proverit(do == posle, 'рабочая база не изменилась: статусов %d до и %d после' % (do, posle))
    uzhe = s.execute("select count(*) from company_comment where body like 'Причина: дубль%'").fetchone()[0]
    print('      сохранено с причиной «дубль» до правки: %d' % uzhe)
    print()
    print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
    raise SystemExit(0)

t = io.open(RCS, encoding='utf-8').read()
staro = '''    "клиент не выходит на связь (3 звонка/2 письма)",
    "дубль",
    "уже купили у конкурентов",'''
novo = '''    "клиент не выходит на связь (3 звонка/2 письма)",
    # «дубль» убран (владелец: «чтобы не плодить очереди»): для дублей есть отдельный
    # результат «Дубль — уже работают» со своей вкладкой
    "уже купили у конкурентов",'''
if 'чтобы не плодить очереди' in t:
    print('уже правлено')
elif t.count(staro) == 1:
    b = os.path.join(KOREN, '_bekap', time.strftime('bez-dublya-%Y%m%d-%H%M%S'))
    os.makedirs(b, exist_ok=True)
    shutil.copy2(RCS, os.path.join(b, 'routes_centro_sales.py'))
    io.open(RCS, 'w', encoding='utf-8').write(t.replace(staro, novo, 1))
    print('правка внесена: «дубль» убран из причин')
else:
    print('ЯКОРЬ: %d вхождений — не правлю' % t.count(staro))
    raise SystemExit(1)

sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
p = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
for l in p.stdout.decode('cp866', 'replace').splitlines():
    if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
        subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'], capture_output=True, timeout=60)
time.sleep(2)
lg = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
lg.write('\n===== перезапуск: «дубль» убран из причин %s =====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
lg.flush()
subprocess.Popen([VENV, os.path.join(KOREN, 'zapusk.py')], cwd=KOREN, stdout=lg,
                 stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200,
                 close_fds=True, env=sreda)
time.sleep(10)
r = subprocess.run([VENV, os.path.abspath(__file__), '--proverka'], capture_output=True,
                   timeout=900, cwd=KOREN, env=sreda)
print()
print('===== ПРОВЕРКА =====')
sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
if r.returncode:
    sys.stdout.write('\n--- stderr ---\n' + r.stderr.decode('utf-8', 'replace')[-3000:])
