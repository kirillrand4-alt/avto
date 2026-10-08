# -*- coding: utf-8 -*-
"""Аккаунты панели Мейера: админ и четыре продавца, с проверкой реального входа.

ПОЧЕМУ ЧЕРЕЗ ФУНКЦИЮ ПАНЕЛИ, А НЕ СВОИМ ХЕШЕМ. Пароли лежат как bcrypt $2b$12$. Если
сочинить формат самой, строки в таблице появятся, выглядеть будут правильно, и войти в
них будет нельзя — ошибка вида «всё создано, ничего не работает». Поэтому зовётся
centro_sales.upsert_user, то есть тот же код, которым панель заводит людей.

ПОЧЕМУ ПРОВЕРКА ВХОДОМ, А НЕ СРАВНЕНИЕМ ХЕША. Хеш может совпадать, а вход всё равно не
работать: роль не из разрешённого списка, is_active=0, своя проверка в маршруте. Поэтому
каждый аккаунт проверяется POST-ом на настоящую форму входа и попыткой открыть страницу.

ЧТО ДЕЛАЕТСЯ СО СТАРЫМИ АККАУНТАМИ. В копии лежат admin, user1..user3, унаследованные с
боевой панели вместе с ИХ паролями. Панель Мейера теперь открыта из интернета, поэтому
старые аккаунты ОТКЛЮЧАЮТСЯ (is_active=0) — но только ПОСЛЕ того, как новый админ
проверен входом, иначе можно запереть владельца снаружи. Строки и их 1638 назначений
остаются на месте: отключение обратимо одной строкой SQL, а удаление — нет.
"""
import logging
import os
import secrets
import sqlite3
import subprocess
import sys
import warnings

# Лог httpx/starlette глушится намеренно: в прошлый прогон он забил хвост ответа
# раннера на шесть килобайт, и пароли, за которыми всё делалось, из вывода пропали.
warnings.filterwarnings('ignore')
for imya_loga in ('httpx', 'httpcore', 'uvicorn', 'uvicorn.error', 'app'):
    logging.getLogger(imya_loga).setLevel(logging.CRITICAL)

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
BAZA = os.path.join(KOREN, 'data', 'centro_sales.db')
PUT = '/obzvon-meyer'

if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:],
                       capture_output=True, timeout=1500,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8',
                                OBZVON_ROOT_PATH=PUT))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace'))
    raise SystemExit(r.returncode)

os.chdir(KOREN)
sys.path.insert(0, KOREN)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(KOREN, '.env'), override=True)
except Exception:  # noqa: BLE001
    pass
os.environ['OBZVON_ROOT_PATH'] = PUT

from app.services import centro_sales as sales  # noqa: E402

itog = []


def skazat(s=''):
    itog.append(str(s))
    print(s)


# ---------------------------------------------------------------- 1. пароли
# Алфавит без пар, которые путают при наборе и диктовке: нет 0/O/o, 1/l/I, 5/S, 2/Z.
ALF = 'acdefghjkmnpqrtuvwxy34679'


def parol():
    return '-'.join(''.join(secrets.choice(ALF) for _ in range(4)) for _ in range(4))


NOVYE = [('meyer_admin', 'admin')] + [('meyer%d' % i, 'sales') for i in range(1, 5)]
paroli = {imya: parol() for imya, _ in NOVYE}

skazat('########## ЗАВОДИМ АККАУНТЫ')
skazat('база продаж копии: %s' % BAZA)
for imya, rol in NOVYE:
    sales.upsert_user(imya, paroli[imya], rol, path=BAZA)
    skazat('   %-12s роль %-6s создан' % (imya, rol))

c = sqlite3.connect(BAZA)
c.row_factory = sqlite3.Row
skazat('всего в таблице users: %d'
       % c.execute('SELECT COUNT(*) FROM users').fetchone()[0])

# ---------------------------------------------------------------- 2. проверка входом
from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

vnesh = create_app()
vnutr = next(z for z in vars(vnesh).values()
             if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))
# Подмену авторизации НЕ ставлю: проверяется настоящий вход.
vnutr.dependency_overrides.clear()


def vhod(imya, par):
    """Вернуть (код логина, код статистики, код главной) для настоящего входа.

    Успех определяется НЕ кодом логина: маршрут отвечает 303 и когда пустил, и когда
    отказал — при отказе он бросает обратно на форму. Признак входа один: после него
    главная страница отдаёт 200, а не редирект на логин.
    """
    with TestClient(vnutr) as k:
        o = k.post('%s/centro/login' % PUT,
                   data={'username': imya, 'password': par},
                   follow_redirects=False)
        kod = o.status_code
        st = k.get('%s/centro/stats' % PUT, follow_redirects=False).status_code
        gl = k.get('%s/centro' % PUT, follow_redirects=False).status_code
        return kod, st, gl


skazat()
skazat('########## ПРОВЕРКА НАСТОЯЩИМ ВХОДОМ')
vse_ok = True
for imya, rol in NOVYE:
    kod, st, gl = vhod(imya, paroli[imya])
    ozhid_st = 200 if rol == 'admin' else 403
    horosho = (gl == 200 and st == ozhid_st)
    vse_ok = vse_ok and horosho
    skazat('   %-12s логин %-4s главная %-4s /stats %-4s (ждём %s)  %s'
           % (imya, kod, gl, st, ozhid_st, 'ОК' if horosho else 'ПЛОХО'))

# Контроль на обратную сторону. Одного положительного замера мало: если проверка пароля
# вообще не работает, все пять «успехов» выше выглядели бы точно так же.
kod, st, gl = vhod('meyer_admin', paroli['meyer_admin'] + 'x')
skazat('   контроль, неверный пароль: главная %s -> %s'
       % (gl, 'НЕ пустил, верно' if gl != 200 else 'ПУСТИЛ, ЭТО ДЫРА'))
kod, st, gl = vhod('net_takogo_cheloveka', 'abc')
skazat('   контроль, нет такого логина:  главная %s -> %s'
       % (gl, 'НЕ пустил, верно' if gl != 200 else 'ПУСТИЛ, ЭТО ДЫРА'))
vse_ok = vse_ok and gl != 200

# ---------------------------------------------------------------- 3. старые аккаунты
skazat()
skazat('########## УНАСЛЕДОВАННЫЕ АККАУНТЫ БОЕВОЙ ПАНЕЛИ')
starye = [r['username'] for r in c.execute(
    "SELECT username FROM users WHERE username NOT LIKE 'meyer%' ORDER BY username")]
skazat('   это: %s' % ', '.join(starye))
if not vse_ok:
    skazat('   новые аккаунты проверку НЕ прошли — старые НЕ отключаю,'
           ' иначе в панель будет не войти')
else:
    c.execute("UPDATE users SET is_active=0, updated_at=? "
              "WHERE username NOT LIKE 'meyer%'", (sales.utcnow(),))
    c.commit()
    skazat('   отключены (is_active=0), строки и назначения сохранены: %d'
           % len(starye))
    # Контроль, что is_active=0 действительно закрывает вход, а не просто красится в
    # таблице. Пароли унаследованных аккаунтов мне неизвестны, поэтому проверка идёт на
    # одноразовом аккаунте с известным паролем, который тут же удаляется.
    proba_par = parol()
    sales.upsert_user('proverka_otkl', proba_par, 'sales', path=BAZA)
    _, _, gl_do = vhod('proverka_otkl', proba_par)
    c.execute("UPDATE users SET is_active=0, updated_at=? WHERE username='proverka_otkl'",
              (sales.utcnow(),))
    c.commit()
    _, _, gl_posle = vhod('proverka_otkl', proba_par)
    c.execute("DELETE FROM users WHERE username='proverka_otkl'")
    c.commit()
    skazat('   контроль is_active: включён -> главная %s, отключён -> главная %s  %s'
           % (gl_do, gl_posle,
              'запрет работает' if (gl_do == 200 and gl_posle != 200)
              else 'ЗАПРЕТ НЕ РАБОТАЕТ'))
    skazat('   одноразовый аккаунт проверки удалён: %s'
           % (c.execute("SELECT COUNT(*) FROM users WHERE username='proverka_otkl'"
                        ).fetchone()[0] == 0))

skazat()
skazat('--- таблица users после всего')
for r in c.execute('SELECT username, role, is_active FROM users ORDER BY '
                   'is_active DESC, role, username'):
    skazat('   %-12s %-6s активен=%s' % (r['username'], r['role'], r['is_active']))

# ---------------------------------------------------------------- 4. выдача
# Печатается В САМОМ КОНЦЕ: ответ раннера обрезается по хвосту, и при обрезке
# сверху пропало бы именно то, за чем всё делалось.
print()
print('===== ЛОГИНЫ И ПАРОЛИ: %s/centro =====' % PUT)
print('%-14s %-8s %s' % ('логин', 'роль', 'пароль'))
for imya, rol in NOVYE:
    print('%-14s %-8s %s' % (imya, rol, paroli[imya]))
print()
print('итог проверки входом: %s' % ('все пять заходят' if vse_ok
                                    else 'ЕСТЬ ПРОБЛЕМЫ, смотри выше'))
