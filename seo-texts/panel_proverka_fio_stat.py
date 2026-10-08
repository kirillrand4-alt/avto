# -*- coding: utf-8 -*-
"""Проверка: перезапуск, все страницы обеими ролями, ФИО на местах, цифры блока против SQL.

Цифры блока сверяются с НЕЗАВИСИМЫМ подсчётом: тот же смысл, но другим способом —
прямым SQL с оконной функцией и json_extract вместо питоновского прохода по журналу.
Если обе дороги дают одно число, ошибиться одинаково в двух местах трудно.
"""
import io
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
import warnings

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
PUT = '/obzvon-meyer'
PORT = 8016
DEN = '2026-08-11'          # самый насыщенный день журнала: 59 записей

if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    # ---------- перезапуск сервера — из внешнего процесса, до проверки
    r = subprocess.run(['netstat', '-ano'], capture_output=True, timeout=90)
    for l in r.stdout.decode('cp866', 'replace').splitlines():
        if (':%d ' % PORT) in l and 'LISTENING' in l.upper():
            subprocess.run(['taskkill', '/PID', l.split()[-1], '/F'],
                           capture_output=True, timeout=60)
    time.sleep(2)
    log = io.open(os.path.join(KOREN, 'centro2.log'), 'a', encoding='utf-8', errors='replace')
    log.write('\n===== перезапуск после ФИО и блока статистики %s =====\n'
              % time.strftime('%Y-%m-%d %H:%M:%S'))
    log.flush()
    subprocess.Popen(
        [VENV, '-m', 'uvicorn', 'app.obzvon:app', '--host', '127.0.0.1', '--port', str(PORT)],
        cwd=KOREN, stdout=log, stderr=subprocess.STDOUT,
        creationflags=0x00000008 | 0x00000200, close_fds=True,
        env=dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH=PUT,
                 ENV_FILE=os.path.join(KOREN, '.env')))
    time.sleep(8)
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:],
                       capture_output=True, timeout=1500,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8', OBZVON_ROOT_PATH=PUT))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    err = r.stderr.decode('utf-8', 'replace')
    if r.returncode:
        sys.stdout.write('\n--- stderr хвост ---\n' + err[-2500:])
    raise SystemExit(r.returncode)

warnings.filterwarnings('ignore')
for n in ('httpx', 'httpcore', 'app'):
    logging.getLogger(n).setLevel(logging.CRITICAL)
os.chdir(KOREN)
sys.path.insert(0, KOREN)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(KOREN, '.env'), override=True)
except Exception:  # noqa: BLE001
    pass
os.environ['OBZVON_ROOT_PATH'] = PUT

from app.api import routes_centro_sales as rcs  # noqa: E402
from app.obzvon import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

itog = []
plohih = 0


def skazat(s=''):
    itog.append(str(s))


def proverit(uslovie, tekst):
    global plohih
    if not uslovie:
        plohih += 1
    skazat('   %s %s' % ('ОК ' if uslovie else 'ПЛОХО', tekst))


vnesh = create_app()
vnutr = next(z for z in vars(vnesh).values()
             if hasattr(z, 'routes') and hasattr(z, 'dependency_overrides'))


def kak(login, rol):
    vnutr.dependency_overrides[rcs.current_user] = lambda: {
        'id': 0, 'username': login, 'role': rol, 'is_active': 1}


def tablica_bloka(html):
    """Строки таблицы блока: {имя: [8 чисел]}."""
    m = re.search(r'<table class="sp-stat-tab">(.*?)</table>', html, re.S)
    if not m:
        return None
    telo = re.search(r'<tbody>(.*?)</tbody>', m.group(1), re.S).group(1)
    rez = {}
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', telo, re.S):
        yach = [re.sub(r'<[^>]+>', '', x).strip()
                for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)]
        if len(yach) == 9:
            imya = re.sub(r'\s*\(отключён\)', '', yach[0]).strip()
            rez[imya] = [int(x) if x.isdigit() else x for x in yach[1:]]
    return rez


# ================================================================ 1. страницы
skazat('########## 1. СТРАНИЦЫ ОБЕИМИ РОЛЯМИ')
STR = ['/centro', '/centro/spisok', '/centro/spisok?stat_data=%s' % DEN,
       '/centro/spisok?stat_data=%s&stat_user=user1' % DEN, '/centro/stats',
       '/centro/stats?user=user2', '/centro/admin', '/centro/park']
html = {}
for login, rol in (('meyer_admin', 'admin'), ('meyer1', 'sales')):
    kak(login, rol)
    with TestClient(vnutr) as k:
        for s in STR:
            o = k.get(PUT + s, follow_redirects=False)
            html[(login, s)] = o.text
            ozhid = 403 if (rol == 'sales' and s.startswith(('/centro/stats', '/centro/admin'))) else 200
            proverit(o.status_code == ozhid, '%-12s %-48s -> %s (ждём %s)'
                     % (login, s, o.status_code, ozhid))

# ================================================================ 2. ФИО
skazat()
skazat('########## 2. ФИО НА МЕСТАХ')
IMENA = ['Пяткова Ксения', 'Ерохин Александр', 'Беляев Максим', 'Волков Роман']
a_sp = html[('meyer_admin', '/centro/spisok')]
proverit(all(i in a_sp for i in IMENA), 'список (админ): все четыре имени в блоке и выборе')
a_st = html[('meyer_admin', '/centro/stats')]
proverit(all(i in a_st for i in IMENA), 'статистика: все четыре имени в таблице продавцов')
a_ad = html[('meyer_admin', '/centro/admin')]
proverit(all(i in a_ad for i in IMENA), 'распределение: все четыре в выборе переназначения')
for s in ('/centro', '/centro/spisok', '/centro/park'):
    proverit('Пяткова Ксения' in html[('meyer1', s)],
             'шапка у meyer1 на %s показывает «Пяткова Ксения»' % s)
# логин не должен торчать там, где теперь имя (в атрибутах value/URL ему место)
vidimyy = re.sub(r'(value|href)="[^"]*"', '', a_sp)
proverit(not re.search(r'>\s*meyer[1-4]\s*<', vidimyy),
         'на списке логин meyer1..4 не виден как текст')

# ================================================================ 3. цифры против SQL
skazat()
skazat('########## 3. ЦИФРЫ БЛОКА ПРОТИВ НЕЗАВИСИМОГО SQL')
c = sqlite3.connect(os.path.join(KOREN, 'data', 'centro_sales.db'))
c.execute("attach database ? as centro", (os.path.join(KOREN, 'data', 'centrifugal.db'),))
VIDNO = ("a.inn in (select inn from centro.company) and "
         "a.inn not in (select inn from hidden_item where kind='company')")

vse = dict(c.execute("select call_result, count(*) from company_assignment a "
                     "join company_state s on s.inn=a.inn and s.username=a.username "
                     "group by 1").fetchall())
ochered_vse = c.execute("select count(*) from company_assignment a left join company_state s "
                        "on s.inn=a.inn and s.username=a.username where s.inn is null and "
                        + VIDNO).fetchone()[0]
# за день: последняя отметка по (владелец, ИНН) за московский день — оконной функцией
den_sql = dict(c.execute("""
    with o as (
      select coalesce(json_extract(payload_json,'$.state_user'), username) vl, inn,
             json_extract(payload_json,'$.result') rez,
             row_number() over (partition by coalesce(json_extract(payload_json,'$.state_user'),
                                username), inn, date(datetime(substr(created_at,1,19),'+3 hours'))
                                order by created_at desc, id desc) nn
      from activity_log
      where action='call_saved'
        and date(datetime(substr(created_at,1,19),'+3 hours')) = ?)
    select rez, count(*) from o where nn=1 group by rez""", (DEN,)).fetchall())

blok = tablica_bloka(a_sp)
blok_den = tablica_bloka(html[('meyer_admin', '/centro/spisok?stat_data=%s' % DEN)])
it = blok.get('Все продавцы') if blok else None
it_d = blok_den.get('Все продавцы') if blok_den else None
skazat('   SQL за всё время: %s, в очереди видимых %d' % (vse, ochered_vse))
skazat('   блок за всё время: %s' % (it[4:] if it else 'НЕТ СТРОКИ'))
if it:
    proverit(it[4] == vse.get('v_rabote', 0), 'взял в работу, всё время: %s = %s' % (it[4], vse.get('v_rabote', 0)))
    proverit(it[5] == vse.get('ne_ponravilas', 0), 'не понравилась, всё время: %s = %s' % (it[5], vse.get('ne_ponravilas', 0)))
    proverit(it[6] == vse.get('dubl', 0), 'дубль, всё время: %s = %s' % (it[6], vse.get('dubl', 0)))
    proverit(it[7] == ochered_vse, 'в очереди, всё время: %s = %s' % (it[7], ochered_vse))
skazat('   SQL за %s: %s' % (DEN, den_sql))
skazat('   блок за %s: %s' % (DEN, it_d[:4] if it_d else 'НЕТ СТРОКИ'))
if it_d:
    proverit(it_d[0] == den_sql.get('v_rabote', 0), 'взял в работу за день: %s = %s' % (it_d[0], den_sql.get('v_rabote', 0)))
    proverit(it_d[1] == den_sql.get('ne_ponravilas', 0), 'не понравилась за день: %s = %s' % (it_d[1], den_sql.get('ne_ponravilas', 0)))
    proverit(it_d[2] == den_sql.get('dubl', 0), 'дубль за день: %s = %s' % (it_d[2], den_sql.get('dubl', 0)))
    # строки по продавцам складываются в итог
    summa = [0] * 8
    for imya, ch in blok_den.items():
        if imya != 'Все продавцы':
            summa = [a + b for a, b in zip(summa, ch)]
    proverit(summa == it_d, 'строки продавцов складываются в итог: %s' % summa)

# видимое по продавцам = «компаний найдено» на списке
vidno_vsego = c.execute("select count(*) from company_assignment a where " + VIDNO).fetchone()[0]
m = re.search(r'<b>([\d\s ]+)</b><span>компаний найдено', a_sp)
naydeno = int(re.sub(r'\D', '', m.group(1))) if m else -1
proverit(vidno_vsego == naydeno, 'видимых назначений %d = «компаний найдено» на списке %d'
         % (vidno_vsego, naydeno))

# ================================================================ 4. починка очереди
skazat()
skazat('########## 4. ОЧЕРЕДЬ НА СТРАНИЦЕ СТАТИСТИКИ')
vidno_u2 = c.execute("select count(*) from company_assignment a where a.username='user2' and "
                     + VIDNO).fetchone()[0]
m = re.search(r'Очередь продавца [^—]*— (\d+) компаний', html[('meyer_admin', '/centro/stats?user=user2')])
v_ocheredi = int(m.group(1)) if m else -1
proverit(v_ocheredi == vidno_u2, 'очередь user2 на статистике %d = видит продавец %d (было 704)'
         % (v_ocheredi, vidno_u2))

# ================================================================ 5. продавец видит только себя
skazat()
skazat('########## 5. ПРОДАВЕЦ ВИДИТ ТОЛЬКО СВОЮ СТРОКУ')
p1 = tablica_bloka(html[('meyer1', '/centro/spisok')])
p2 = tablica_bloka(html[('meyer1', '/centro/spisok?stat_data=%s&stat_user=user1' % DEN)])
proverit(p1 is not None and list(p1) == ['Пяткова Ксения'], 'meyer1 видит одну строку: %s' % (list(p1) if p1 else p1))
proverit(p2 is not None and list(p2) == ['Пяткова Ксения'],
         'meyer1 с подставленным stat_user=user1 всё равно видит только себя: %s' % (list(p2) if p2 else p2))
proverit('name="stat_user"' not in html[('meyer1', '/centro/spisok')], 'у продавца нет выбора продавца')

# ================================================================ 6. фильтры не теряются
skazat()
skazat('########## 6. ФИЛЬТРЫ СПИСКА И ДАТА БЛОКА НЕ СБРАСЫВАЮТ ДРУГ ДРУГА')
kak('meyer_admin', 'admin')
with TestClient(vnutr) as k:
    t = k.get(PUT + '/centro/spisok?region=Москва&stat_data=%s&stat_user=user1' % DEN).text
proverit('name="region" value="Москва"' in t, 'форма блока помнит фильтр региона')
proverit('name="stat_data" value="%s"' % DEN in t, 'форма фильтров помнит дату блока')
proverit(re.search(r'href="[^"]*stat_data=%s[^"]*"' % DEN, t) is not None,
         'ссылки сортировки и страниц несут дату блока')

io.open(r'C:\seostat\drop\drop-storage\centro2-spisok-statblok.html', 'w',
        encoding='utf-8').write(html[('meyer_admin', '/centro/spisok?stat_data=%s' % DEN)])

print('===== ИТОГ ПРОВЕРКИ =====')
for s in itog:
    print(s)
print()
print('ПЛОХИХ ПРОВЕРОК: %d' % plohih)
