# -*- coding: utf-8 -*-
"""Проверка статистики ДО перезапуска: типы строк каталога, SQL, рендер шаблона.

Зачем не сразу через HTTP: ошибка Jinja или `.get` на sqlite3.Row вылезет как 500 в
логе, а в логе я увижу только хвост. Дешевле проверить в том же процессе и починить.
"""
import io
import os
import subprocess
import sys
import traceback

# Раннер запускает системным питоном, а там нет ни fastapi, ни jinja2, ни bcrypt
# (на этом уже спотыкался запуск копии). Поэтому скрипт сам себя перезапускает тем
# интерпретатором, которым живёт панель.
VENV = r'C:\seostat\.venv\Scripts\python.exe'
if os.path.normcase(VENV) != os.path.normcase(sys.executable):
    sreda = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([VENV, os.path.abspath(__file__)] + sys.argv[1:],
                       capture_output=True, timeout=1500, env=sreda)
    sys.stdout.write(r.stdout.decode('utf-8', 'replace'))
    sys.stderr.write(r.stderr.decode('utf-8', 'replace'))
    raise SystemExit(r.returncode)

os.chdir(r'C:\centro2')
sys.path.insert(0, r'C:\centro2')
os.environ.setdefault('ENV_FILE', r'C:\centro2\.env')

otchet = []


def skazat(s):
    otchet.append(s)
    print(s)


try:
    from dotenv import load_dotenv
    load_dotenv(r'C:\centro2\.env', override=True)
except Exception as e:  # noqa: BLE001
    skazat('dotenv: %s' % e)

from app.api import routes_centro_sales as rcs  # noqa: E402

skazat('модуль импортирован: %s' % rcs.__file__)
skazat('базы: CENTRIFUGAL_DB=%s' % os.environ.get('CENTRIFUGAL_DB'))
skazat('       CENTRO_SALES_DB=%s' % os.environ.get('CENTRO_SALES_DB'))

# --- 1. какие объекты возвращает каталог: dict или sqlite3.Row
try:
    spisok = rcs.catalog.list_companies()
    skazat('list_companies: %d строк, тип строки %s, есть .get: %s'
           % (len(spisok), type(spisok[0]).__name__ if spisok else '-',
              hasattr(spisok[0], 'get') if spisok else '-'))
    if spisok:
        klyuchi = (list(spisok[0].keys()) if hasattr(spisok[0], 'keys')
                   else dir(spisok[0]))
        skazat('  поля: %s' % ', '.join([str(k) for k in klyuchi][:18]))
except Exception:  # noqa: BLE001
    skazat('list_companies ПАДАЕТ:\n%s' % traceback.format_exc()[-1200:])
    spisok = []

# --- 2. SQL статистики
imena = {}
vsego = 0
for row in spisok:
    inn = str((row.get('inn') if hasattr(row, 'get') else row['inn']) or '').strip()
    if not inn:
        continue
    vsego += 1
    imena[inn] = ''
try:
    with rcs.sales.connect() as conn:
        obshchee = rcs._stats_obshchee(conn)
        prodavcy = rcs._stats_po_prodavcam(conn)
        pervyy = prodavcy[0]['username'] if prodavcy else ''
        ochered = rcs._stats_ochered(conn, pervyy, imena) if pervyy else []
    obshchee['v_kataloge'] = vsego
    obshchee['ne_naznacheno'] = max(0, vsego - obshchee['naznacheno'])
    skazat('SQL отработал. в каталоге %d, назначено %d, обработано %d, просрочено %d'
           % (vsego, obshchee['naznacheno'], obshchee['obrabotano'],
              obshchee['prosrocheno']))
    skazat('  продавцов %d, очередь первого (%s) = %d строк'
           % (len(prodavcy), pervyy, len(ochered)))
    for p in prodavcy:
        skazat('   %-14s роль %-8s назначено %5d обработано %5d просрочено %4d'
               % (p['username'], p['role'], p['naznacheno'], p['obrabotano'],
                  p['prosrocheno']))
except Exception:  # noqa: BLE001
    skazat('SQL ПАДАЕТ:\n%s' % traceback.format_exc()[-1800:])
    obshchee, prodavcy, ochered, pervyy = {}, [], [], ''

# --- 3. рендер шаблона тем же окружением Jinja, что у приложения
try:
    shablon = rcs.templates.get_template('centro_stats.html')
    html = shablon.render({
        'user': {'username': 'proverka', 'role': 'admin'},
        'obshchee': obshchee, 'prodavcy': prodavcy, 'ochered': ochered,
        'vybrannyy': pervyy, 'metki': rcs.sales.CALL_RESULT_LABELS,
        'poisk_param': getattr(rcs, '_STATS_POISK', 'inn'),
        'base_path': rcs.BP,
    })
    skazat('шаблон отрендерен: %d знаков, строк таблицы очереди %d'
           % (len(html), html.count('<tr>')))
    io.open(r'C:\seostat\drop\drop-storage\centro2-stats-proba.html', 'w',
            encoding='utf-8').write(html)
    skazat('  образец положен на дроп: centro2-stats-proba.html')
except Exception:  # noqa: BLE001
    skazat('ШАБЛОН ПАДАЕТ:\n%s' % traceback.format_exc()[-1800:])

# --- 4. маршрут зарегистрирован в приложении
try:
    from app.obzvon import create_app
    prilozhenie = create_app()
    puti = sorted({getattr(r, 'path', '') for r in prilozhenie.routes})
    est = [p for p in puti if 'stats' in p]
    skazat('маршрутов в приложении %d, со словом stats: %s' % (len(puti), est or 'НЕТ'))
except Exception:  # noqa: BLE001
    skazat('create_app ПАДАЕТ:\n%s' % traceback.format_exc()[-1500:])

print('\n===== ИТОГ =====')
for s in otchet[-14:]:
    print(s)
