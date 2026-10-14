# -*- coding: utf-8 -*-
"""fixV (14.10): три руководителя отдела продаж панели Meyer (роль rop, код – fixV_kod.py).
Барнаул – Погорелый Александр, Воронеж – Шамшев Вячеслав, Краснодар – Ершов Михаил.

Как panel_polzovateli_meyer2.py: аккаунт заводится функцией самой панели centro_sales.upsert_user
(bcrypt), ФИО – users.fio, город – users.gorod (по городу панель собирает команду: действующие
менеджеры role='sales' того же города). Пароли генерируются здесь и печатаются ТОЛЬКО в самом конце
вывода (в файлы, на дроп и в журнал не пишутся; в базе – только хеш). Проверка – настоящим входом
через TestClient на живом коде и живой базе: главная 200, статистика 200, шапка, в статистике только
команда, попытка действия – 403 (запрос выбран так, что и без запрета ничего бы не записал), неверный
пароль не пускает. Перед записью – копия базы продаж. Повторный запуск существующие логины не трогает.
"""
import io
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.request
import warnings

warnings.filterwarnings('ignore')
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
PUT = '/obzvon-meyer'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:], capture_output=True, timeout=1500,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace')[-3000:])
    raise SystemExit(r.returncode)
sys.path.insert(0, KOREN)
import zapusk  # noqa: E402,F401  – .env панели в окружение (живые базы)
logging.disable(logging.CRITICAL)
from app.services import centro_sales as sales  # noqa: E402
NOVYE = [('meyer_rop_barnaul', 'Погорелый Александр', 'Барнаул'),
         ('meyer_rop_voronezh', 'Шамшев Вячеслав', 'Воронеж'),
         ('meyer_rop_krasnodar', 'Ершов Михаил', 'Краснодар')]
ALF = 'acdefghjkmnpqrtuvwxy34679'          # без 0/O/o, 1/l/I, 5/S, 2/Z, b/6, 8/B
VREMYA = time.strftime('%Y%m%d-%H%M%S')
LOG = []


def pech(s=''):
    print(s)
    LOG.append(s)


def parol():
    return '-'.join(''.join(secrets.choice(ALF) for _ in range(4)) for _ in range(4))


BAZA = str(sales.sales_db_path())
pech('база продаж: %s' % BAZA)
assert os.path.normcase(BAZA) == os.path.normcase(os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')), BAZA
assert 'rop' in sales.ROLES, 'код fixV не стоит'
c = sqlite3.connect(BAZA, timeout=30)
c.row_factory = sqlite3.Row
sx = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
assert "'rop'" in sx, 'CHECK роли без rop – сначала fixV_kod.py --primenit'
papka = os.path.join(KOREN, '_bekap', 'fixV-polz-' + VREMYA)
os.makedirs(papka, exist_ok=True)
b = sqlite3.connect(os.path.join(papka, 'centro_sales_meyer1.db'))
c.backup(b)
b.close()
pech('копия базы продаж: %s' % papka)
uzhe = {r['username'] for r in c.execute('SELECT username FROM users')}
paroli = {}
for login, fio, gorod in NOVYE:
    if login in uzhe:
        pech('   %s уже есть – пароль не трогаю' % login)
        continue
    paroli[login] = parol()
    sales.upsert_user(login, paroli[login], 'rop', path=BAZA)
    c.execute('UPDATE users SET fio=?, gorod=?, is_active=1 WHERE username=?', (fio, gorod, login))
    c.commit()
    pech('   %-20s %-20s %-10s создан' % (login, fio, gorod))
lyudi = {r['username']: dict(r) for r in c.execute('SELECT username, role, is_active, fio, gorod FROM users')}
for r in c.execute("SELECT username, role, is_active, fio, gorod, length(password_hash) n, "
                   "substr(password_hash,1,4) p FROM users WHERE role='rop' ORDER BY username"):
    pech('   в базе: %-20s роль %s, активен %s, %s, %s, хеш bcrypt %s… (%d знаков)'
         % (r['username'], r['role'], r['is_active'], r['fio'], r['gorod'], r['p'], r['n']))

from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides.clear()
plohih = [0]


def ok(u, t):
    if not u:
        plohih[0] += 1
    pech('   %s %s' % ('ОК ' if u else 'ПЛОХО', t))


def kolvo():
    return [c.execute('SELECT COUNT(*) FROM %s' % t).fetchone()[0]
            for t in ('activity_log', 'company_state', 'company_comment', 'hidden_item', 'company_assignment')]


fio = {u: (r['fio'] or u) for u, r in lyudi.items()}
for login, fio_rop, gorod in NOVYE:
    kom = sorted(u for u, r in lyudi.items() if r['role'] == 'sales' and r['is_active']
                 and (r['gorod'] or '').strip() == gorod)
    chuzhie = sorted(u for u, r in lyudi.items() if r['role'] == 'sales' and r['is_active'] and u not in kom)
    pech('-- %s: команда %s' % (login, ', '.join('%s %s' % (u, fio[u]) for u in kom)))
    if login not in paroli:
        pech('   пароль не менялся – вход не проверяю')
        continue
    with TestClient(vnutr) as kl:
        o = kl.post(PUT + '/centro/login', data={'username': login, 'password': paroli[login]}, follow_redirects=False)
        g = kl.get(PUT + '/centro', follow_redirects=False)
        s = kl.get(PUT + '/centro/stats', follow_redirects=False)
        ok(g.status_code == 200 and s.status_code == 200,
           'вход %s: форма %s, главная %s, статистика %s' % (login, o.status_code, g.status_code, s.status_code))
        h = s.text
        ok('%s · Руководитель отдела продаж · %s' % (fio_rop, gorod) in h, 'шапка «%s · Руководитель отдела продаж · %s»' % (fio_rop, gorod))
        h2 = re.sub(r'передал компанию:[^<]*', '', h)
        ok(all(fio[u] in h2 for u in kom) and not [fio[u] for u in chuzhie if fio[u] in h2],
           'статистика: команда есть, чужих нет (%s)' % [fio[u] for u in chuzhie if fio[u] in h2])
        vybor = re.findall(r'<select name="assigned_user".*?</select>', g.text, re.S)
        ok(vybor and not [u for u in chuzhie for v in vybor if 'value="%s"' % u in v],
           'главная: в выборе менеджера только команда')
        do_ = kolvo()
        # запросы, которые и без запрета ничего бы не записали: неизвестный результат, пустой логин
        p1 = kl.post(PUT + '/centro/save', data={'inn': '0000000000', 'call_result': 'fixV_proverka'}, follow_redirects=False)
        p2 = kl.post(PUT + '/centro/reassign', data={'inn': '0000000000', 'username': ''}, follow_redirects=False)
        ok(p1.status_code == 403 and p2.status_code == 403 and kolvo() == do_,
           'действия запрещены: сохранение %s, переназначение %s; база не изменилась' % (p1.status_code, p2.status_code))
        a = kl.get(PUT + '/centro/admin', follow_redirects=False)
        ok(a.status_code == 403, '«Распределение»: %s' % a.status_code)
if paroli:
    l0 = next(iter(paroli))
    with TestClient(vnutr) as kl:
        kl.post(PUT + '/centro/login', data={'username': l0, 'password': paroli[l0] + 'x'}, follow_redirects=False)
        g = kl.get(PUT + '/centro', follow_redirects=False).status_code
    ok(g != 200, 'контроль: неверный пароль -> главная %s (не пустил)' % g)
try:
    k = urllib.request.urlopen('http://127.0.0.1:8016%s/centro/login' % PUT, timeout=30).status
except Exception as e:  # noqa: BLE001
    k = str(e)[:80]
ok(k == 200, 'живая панель: форма входа %s' % k)
pech('итог: %s' % ('ВСЕ НОВЫЕ ВХОДЯТ, ПЛОХИХ 0' if not plohih[0] else 'ПЛОХИХ ПРОВЕРОК: %d' % plohih[0]))
io.open(os.path.join(r'C:\seostat\drop\drop-storage', 'fixV-polzovateli-%s.txt' % VREMYA), 'w',
        encoding='utf-8').write('\n'.join(LOG) + '\n(пароли в этот файл не пишутся)\n')
c.close()
print('\n===== НОВЫЕ ЛОГИНЫ (%s/centro) =====' % PUT)
for login, fio_, gorod in NOVYE:
    if login in paroli:
        print('%-20s %-20s %-10s %s' % (login, fio_, gorod, paroli[login]))
