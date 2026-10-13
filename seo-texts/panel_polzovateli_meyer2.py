# -*- coding: utf-8 -*-
"""Пять новых продавцов панели Meyer (владелец 13.10: «добавь 5 юзеров»):
Воронеж – Козлов Андрей, Тюнин Артем; Барнаул – Иванов Вадим, Кузнецова Ирина, Кузьмин Юрий.

Как первые четыре (panel_polzovateli_meyer.py): аккаунт заводится функцией самой панели
centro_sales.upsert_user (bcrypt), ФИО – в users.fio (фамилия первой, как у остальных),
город – в новой колонке users.gorod (справочно). Пароли генерируются здесь и печатаются
ТОЛЬКО в конце вывода (в файлы и на дроп не пишутся; в базе – только хеш). Проверка –
настоящим входом через TestClient: главная 200, статистика 403 (продавец), неверный пароль
не пускает. Компании новым продавцам этот скрипт НЕ раздаёт.
Повторный запуск не трогает уже существующие логины (пароль не меняет).
"""
import logging, os, secrets, sqlite3, subprocess, sys, warnings
warnings.filterwarnings('ignore')
for n in ('httpx', 'httpcore', 'uvicorn', 'uvicorn.error', 'app'):
    logging.getLogger(n).setLevel(logging.CRITICAL)
VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
PUT = '/obzvon-meyer'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:], capture_output=True, timeout=1500,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH=PUT))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace')[-3000:])
    raise SystemExit(r.returncode)
os.chdir(KOREN)
sys.path.insert(0, KOREN)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(KOREN, '.env'), override=True)
os.environ['OBZVON_ROOT_PATH'] = PUT
from app.services import centro_sales as sales  # noqa: E402
BAZA = os.environ.get('CENTRO_SALES_DB') or os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
NOVYE = [('meyer5', 'Козлов Андрей', 'Воронеж'), ('meyer6', 'Тюнин Артем', 'Воронеж'),
         ('meyer7', 'Иванов Вадим', 'Барнаул'), ('meyer8', 'Кузнецова Ирина', 'Барнаул'),
         ('meyer9', 'Кузьмин Юрий', 'Барнаул')]
ALF = 'acdefghjkmnpqrtuvwxy34679'


def parol():
    return '-'.join(''.join(secrets.choice(ALF) for _ in range(4)) for _ in range(4))


print('база продаж:', os.path.basename(BAZA))
c = sqlite3.connect(BAZA)
c.row_factory = sqlite3.Row
kol = [x[1] for x in c.execute('pragma table_info(users)')]
if 'gorod' not in kol:
    c.execute('ALTER TABLE users ADD COLUMN gorod TEXT')
    c.commit()
uzhe = {r['username'] for r in c.execute('select username from users')}
paroli = {}
for login, fio, gorod in NOVYE:
    if login in uzhe:
        print('   %s уже есть – не трогаю' % login)
        continue
    paroli[login] = parol()
    sales.upsert_user(login, paroli[login], 'sales', path=BAZA)
    c.execute('UPDATE users SET fio=?, gorod=?, is_active=1 WHERE username=?', (fio, gorod, login))
    c.commit()
    print('   %-7s %-16s %-8s создан' % (login, fio, gorod))

from app.api import routes_centro_sales as rcs  # noqa: E402,F401
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
vnutr = next(z for z in vars(create_app()).values() if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
vnutr.dependency_overrides.clear()


def vhod(login, par):
    with TestClient(vnutr) as k:
        k.post('%s/centro/login' % PUT, data={'username': login, 'password': par}, follow_redirects=False)
        return k.get('%s/centro' % PUT, follow_redirects=False).status_code, \
            k.get('%s/centro/stats' % PUT, follow_redirects=False).status_code


vse_ok = True
for login, par in paroli.items():
    gl, st = vhod(login, par)
    ok = gl == 200 and st == 403
    vse_ok = vse_ok and ok
    print('   вход %-7s главная %s, статистика %s  %s' % (login, gl, st, 'ОК' if ok else 'ПЛОХО'))
if paroli:
    l0 = next(iter(paroli))
    gl, _ = vhod(l0, paroli[l0] + 'x')
    print('   контроль: неверный пароль -> главная %s (%s)' % (gl, 'не пустил, верно' if gl != 200 else 'ПУСТИЛ'))
    vse_ok = vse_ok and gl != 200
print('\n--- продавцы панели')
for r in c.execute("select username, fio, coalesce(gorod,'') g, is_active from users where role='sales' and is_active=1 order by username"):
    n = c.execute('select count(*) from company_assignment where username=?', (r['username'],)).fetchone()[0]
    print('   %-7s %-18s %-8s компаний %d' % (r['username'], r['fio'] or '', r['g'], n))
print('\n===== НОВЫЕ ЛОГИНЫ (%s/centro) =====' % PUT)
for login, fio, gorod in NOVYE:
    if login in paroli:
        print('%-7s %-16s %-8s %s' % (login, fio, gorod, paroli[login]))
print('итог: %s' % ('все новые входят' if vse_ok else 'ЕСТЬ ПРОБЛЕМЫ'))
