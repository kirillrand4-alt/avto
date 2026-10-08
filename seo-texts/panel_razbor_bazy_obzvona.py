# -*- coding: utf-8 -*-
"""Как устроены «базы обзвона»: откуда берётся имя centro и есть ли их реестр.

Если centro — это ЗНАЧЕНИЕ параметра маршрута (имя базы обзвона), а не литерал в пути,
то правильный ход это не переименование строк, а регистрация базы с именем meyer. Тогда
путь получится штатным, как и задумано автором панели, а не выломанным поверх.
"""
import io
import os
import re

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-bazy-obzvona.txt'
vyhod = []
svodka = []


def pishi(s=''):
    vyhod.append(str(s))


def svodno(s):
    svodka.append(str(s))
    vyhod.append(str(s))


def pokazat(put, ot, do, zagolovok):
    pishi()
    pishi('########## %s  (%s, строки %d-%d)' % (zagolovok, os.path.basename(put), ot, do))
    stroki = io.open(put, encoding='utf-8', errors='replace').read().splitlines()
    for i, l in enumerate(stroki, 1):
        if ot <= i <= do:
            pishi('   %4d: %s' % (i, l.rstrip()[:175]))


RC = os.path.join(KOREN, 'app', 'api', 'routes_centro.py')
RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
RP = os.path.join(KOREN, 'app', 'api', 'routes_park.py')
CONF = os.path.join(KOREN, 'app', 'config.py')

# ---------------------------------------------------------------- 1. все пути маршрутов
pishi('########## ВСЕ ПУТИ МАРШРУТОВ')
vsego = 0
for f in sorted(os.listdir(os.path.join(KOREN, 'app', 'api'))):
    if not f.endswith('.py'):
        continue
    p = os.path.join(KOREN, 'app', 'api', f)
    t = io.open(p, encoding='utf-8', errors='replace').read()
    nashli = re.findall(r'@router\.(get|post|put|delete)\(\s*([^\n]+)', t)
    if not nashli:
        continue
    pishi('--- %s' % f)
    for metod, hvost in nashli:
        vsego += 1
        pishi('   %-6s %s' % (metod.upper(), hvost.strip().rstrip(',')[:150]))
svodno('маршрутов всего: %d' % vsego)

# есть ли catch-all с параметром base
for imya, p in (('routes_centro.py', RC), ('routes_centro_sales.py', RCS),
                ('routes_park.py', RP)):
    t = io.open(p, encoding='utf-8', errors='replace').read()
    cat = re.findall(r'@router\.\w+\([^)]*\{base[^)]*\)', t)
    svodno('%s: маршрутов с {base}: %d' % (imya, len(cat)))
    for c in cat[:6]:
        pishi('   catch-all: %s' % re.sub(r'\s+', ' ', c)[:170])

# ---------------------------------------------------------------- 2. реестр баз
pishi()
pishi('########## ПОИСК РЕЕСТРА БАЗ ОБЗВОНА')
nashlos = 0
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in sorted(fajly):
        if not f.endswith('.py'):
            continue
        p = os.path.join(kor, f)
        t = io.open(p, encoding='utf-8', errors='replace').read()
        for i, l in enumerate(t.splitlines(), 1):
            if re.search(r'(BAZY|BASES|BAZA|базы обзвона|Неизвестная база|'
                         r'["\']centro["\']|["\']centro1["\'])', l):
                nashlos += 1
                pishi('   %s:%d  %s' % (os.path.relpath(p, KOREN), i, l.strip()[:165]))
svodno('строк, похожих на реестр баз: %d' % nashlos)

# ---------------------------------------------------------------- 3. куски файлов
pokazat(CONF, 50, 95, 'config.py: obzvon_root_path и соседи')
pokazat(RC, 40, 75, 'routes_centro.py: про базы обзвона')
pokazat(RC, 120, 150, 'routes_centro.py: префикс и роутер')
pokazat(RC, 925, 960, 'routes_centro.py: catch-all')
pokazat(RP, 260, 275, 'routes_park.py: ссылка на /centro/park')

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('полный разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СВОДКА =====')
for s in svodka:
    print(s)
