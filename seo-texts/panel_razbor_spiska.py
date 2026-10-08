# -*- coding: utf-8 -*-
"""Страница «Список компаний» и можно ли честно считать статистику НА ДАТУ.

Главный вопрос — про дату. Есть два источника:
  company_state.last_contact_at — время ПОСЛЕДНЕГО действия по компании. По нему «за
     вчера» посчитается неверно, если ту же компанию трогали сегодня: вчерашняя отметка
     пропадёт, и число за вчера будет занижаться задним числом.
  activity_log — история действий. По ней дата считается честно, НО только если там
     записан результат звонка, а не просто факт захода.
Поэтому смотрю, что реально лежит в activity_log, прежде чем обещать разрез по датам.
"""
import io
import json
import os
import re
import sqlite3

KOREN = r'C:\centro2'
BAZA = os.path.join(KOREN, 'data', 'centro_sales.db')
OTCHET = r'C:\seostat\drop\drop-storage\razbor-spiska.txt'
vyhod = []
svodka = []


def pishi(s=''):
    vyhod.append(str(s))


def svodno(s):
    svodka.append(str(s))
    vyhod.append(str(s))


# ---------------------------------------------------------------- 1. activity_log
c = sqlite3.connect(BAZA)
c.row_factory = sqlite3.Row
pishi('########## activity_log')
kol = [r['name'] for r in c.execute('PRAGMA table_info(activity_log)')]
svodno('колонки activity_log: %s' % ', '.join(kol))
pishi('   DDL: %s' % re.sub(r'\s+', ' ', c.execute(
    "SELECT sql FROM sqlite_master WHERE name='activity_log'").fetchone()[0])[:400])
pishi()
pishi('--- 6 свежих записей целиком')
for r in c.execute('SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 6'):
    pishi('   %s' % json.dumps(dict(r), ensure_ascii=False)[:300])
# какие вообще бывают действия
for pole in ('action', 'event', 'kind', 'type', 'what', 'call_result', 'result'):
    if pole in kol:
        raskl = list(c.execute(
            'SELECT %s, COUNT(*) FROM activity_log GROUP BY 1 ORDER BY 2 DESC LIMIT 12'
            % pole))
        svodno('activity_log.%s: %s' % (pole, [(r[0], r[1]) for r in raskl]))
pishi()
pishi('--- по датам')
for r in c.execute("SELECT substr(created_at,1,10) d, COUNT(*) n FROM activity_log "
                   'GROUP BY 1 ORDER BY 1 DESC LIMIT 8'):
    pishi('   %s  %d' % (r['d'], r['n']))

pishi()
pishi('########## company_state')
kol2 = [r['name'] for r in c.execute('PRAGMA table_info(company_state)')]
svodno('колонки company_state: %s' % ', '.join(kol2))
raskl = list(c.execute('SELECT call_result, COUNT(*) FROM company_state '
                       'GROUP BY 1 ORDER BY 2 DESC'))
svodno('company_state.call_result: %s' % [(r[0], r[1]) for r in raskl])
pishi('--- 4 свежие строки')
for r in c.execute('SELECT * FROM company_state ORDER BY last_contact_at DESC LIMIT 4'):
    pishi('   %s' % json.dumps(dict(r), ensure_ascii=False)[:300])

# сходится ли одно с другим: можно ли по журналу восстановить нынешние статусы
if 'call_result' in kol or 'result' in kol:
    pole = 'call_result' if 'call_result' in kol else 'result'
    n = c.execute('SELECT COUNT(*) FROM activity_log WHERE %s IS NOT NULL AND %s<>""'
                  % (pole, pole)).fetchone()[0]
    svodno('записей журнала с результатом звонка: %d из %d'
           % (n, c.execute('SELECT COUNT(*) FROM activity_log').fetchone()[0]))

# ---------------------------------------------------------------- 2. страница списка
pishi()
pishi('########## МАРШРУТ /centro/spisok')
RP = os.path.join(KOREN, 'app', 'api', 'routes_park.py')
t = io.open(RP, encoding='utf-8', errors='replace').read().splitlines()
nach = None
for i, l in enumerate(t, 1):
    if re.search(r'@router\.get\(.*?/centro/spisok|def spisok', l):
        nach = i
        break
if nach:
    for j in range(nach - 2, min(len(t), nach + 70)):
        pishi('   %4d: %s' % (j + 1, t[j].rstrip()[:175]))
    svodno('маршрут списка найден в routes_park.py:%d' % nach)
else:
    svodno('маршрут списка НЕ найден по образцу')
    for i, l in enumerate(t, 1):
        if 'spisok' in l:
            pishi('   %4d: %s' % (i, l.rstrip()[:170]))

# чем отдаётся шаблон — какой контекст
for i, l in enumerate(t, 1):
    if 'spisok.html' in l:
        pishi()
        pishi('--- отдача шаблона spisok.html, %s:%d' % ('routes_park.py', i))
        for j in range(max(0, i - 30), min(len(t), i + 6)):
            pishi('   %4d: %s' % (j + 1, t[j].rstrip()[:175]))

# ---------------------------------------------------------------- 3. шапка со счётчиками
pishi()
pishi('########## spisok.html: БЛОК СЧЁТЧИКОВ')
SH = os.path.join(KOREN, 'app', 'templates', 'spisok.html')
ht = io.open(SH, encoding='utf-8', errors='replace').read().splitlines()
svodno('spisok.html: %d строк' % len(ht))
for i, l in enumerate(ht, 1):
    if re.search(r'компаний найдено|с выручкой|с техконтактом|в работе|'
                 r'суммарная выручка|class="(svodka|stats|counters|metrics)', l):
        pishi('   %4d: %s' % (i, l.rstrip()[:175]))
pishi()
pishi('--- первые 60 строк шаблона')
for i, l in enumerate(ht[:60], 1):
    pishi('   %4d: %s' % (i, l.rstrip()[:175]))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('полный разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СВОДКА =====')
for s in svodka:
    print(s)
