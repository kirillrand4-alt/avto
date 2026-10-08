# -*- coding: utf-8 -*-
"""Последние факты перед правкой: время назначения, скрытые в очереди, шаблоны, фильтр.

1) Есть ли у назначения время (assigned_at/created_at). Без него «в очереди на конец
   дня» считается по НЫНЕШНЕМУ распределению — это надо знать и написать под таблицей.
2) Убирает ли очередь продавца скрытые компании. Если да, а моя страница статистики их
   не убирала, то в ней очередь user2 = 704 завышена, и это надо чинить заодно.
3) Сколько объектов Jinja2Templates в модулях — фильтр |fio надо повесить на каждый,
   иначе в половине шаблонов он упадёт с «No filter named 'fio'».
4) Как выглядит выпадающий «Продавец» на списке — там тоже надо показать ФИО.
"""
import io
import os
import re
import sqlite3

KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-ocheredi.txt'
vyhod = []
svodka = []


def pishi(s=''):
    vyhod.append(str(s))


def svodno(s):
    svodka.append(str(s))
    vyhod.append(str(s))


c = sqlite3.connect(os.path.join(KOREN, 'data', 'centro_sales.db'))
c.row_factory = sqlite3.Row
kol = [r['name'] for r in c.execute('PRAGMA table_info(company_assignment)')]
svodno('колонки company_assignment: %s' % ', '.join(kol))

# скрытые среди назначенных, по продавцам
for r in c.execute(
        "SELECT a.username, COUNT(*) vsego, "
        "SUM(CASE WHEN h.inn IS NOT NULL THEN 1 ELSE 0 END) skryto "
        "FROM company_assignment a LEFT JOIN (SELECT DISTINCT inn FROM hidden_item "
        "WHERE kind='company') h ON h.inn=a.inn GROUP BY a.username"):
    svodno('  %s: назначено %d, из них скрыто %d, видно %d'
           % (r['username'], r['vsego'], r['skryto'], r['vsego'] - r['skryto']))

# состояния: совпадает ли username состояния с владельцем назначения
r = c.execute(
    "SELECT COUNT(*) n, SUM(CASE WHEN s.username=a.username THEN 1 ELSE 0 END) sovp "
    "FROM company_state s JOIN company_assignment a ON a.inn=s.inn").fetchone()
svodno('состояний с назначением: %d, у владельца назначения: %d' % (r['n'], r['sovp']))
r = c.execute("SELECT COUNT(*) FROM company_state s WHERE NOT EXISTS "
              "(SELECT 1 FROM company_assignment a WHERE a.inn=s.inn)").fetchone()[0]
svodno('состояний без назначения: %d' % r)
r = c.execute("SELECT COUNT(*) FROM (SELECT inn FROM company_state GROUP BY inn "
              "HAVING COUNT(*)>1)").fetchone()[0]
svodno('ИНН с несколькими состояниями: %d' % r)

# обработанные среди скрытых
r = c.execute("SELECT COUNT(*) FROM company_state s WHERE s.inn IN "
              "(SELECT inn FROM hidden_item WHERE kind='company')").fetchone()[0]
svodno('обработанных среди скрытых: %d' % r)

# ---------------------------------------------------------------- очередь в карточке
RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
t = io.open(RCS, encoding='utf-8', errors='replace').read()
pishi()
pishi('########## УПОМИНАНИЯ hidden В routes_centro_sales.py')
for i, l in enumerate(t.splitlines(), 1):
    if re.search(r'hidden|skryt|скрыт', l, re.I):
        pishi('   %4d: %s' % (i, l.strip()[:165]))
n_hid = len(re.findall(r'hidden', t))
svodno('упоминаний hidden в маршрутах продаж: %d' % n_hid)
# где вызывается _queue_rank
for i, l in enumerate(t.splitlines(), 1):
    if '_queue_rank' in l:
        pishi('   _queue_rank %4d: %s' % (i, l.strip()[:150]))

# ---------------------------------------------------------------- Jinja2Templates
pishi()
pishi('########## ОБЪЕКТЫ Jinja2Templates')
for kor, kat, fajly in os.walk(os.path.join(KOREN, 'app')):
    kat[:] = [d for d in kat if '__pycache__' not in d and 'dokaz' not in d]
    for f in sorted(fajly):
        if not f.endswith('.py'):
            continue
        p = os.path.join(kor, f)
        tt = io.open(p, encoding='utf-8', errors='replace').read()
        for i, l in enumerate(tt.splitlines(), 1):
            if 'Jinja2Templates(' in l or re.search(r'^templates\s*=', l) \
                    or re.search(r'from .* import .*\btemplates\b', l) \
                    or 'env.filters[' in l or 'env.globals[' in l:
                pishi('   %s:%d  %s' % (os.path.relpath(p, KOREN), i, l.strip()[:150]))
                if 'Jinja2Templates(' in l:
                    svodno('Jinja2Templates в %s:%d' % (f, i))

# где вызывается _ensure_assignment_columns
CS = os.path.join(KOREN, 'app', 'services', 'centro_sales.py')
tt = io.open(CS, encoding='utf-8', errors='replace').read()
for i, l in enumerate(tt.splitlines(), 1):
    if '_ensure_assignment_columns(' in l and 'def ' not in l:
        svodno('_ensure_assignment_columns вызывается: centro_sales.py:%d  %s'
               % (i, l.strip()[:90]))

# ---------------------------------------------------------------- фильтр «Продавец»
pishi()
pishi('########## spisok.html, строки 60-110')
SH = os.path.join(KOREN, 'app', 'templates', 'spisok.html')
ht = io.open(SH, encoding='utf-8', errors='replace').read().splitlines()
for i, l in enumerate(ht, 1):
    if 60 <= i <= 110:
        pishi('   %4d: %s' % (i, l.rstrip()[:180]))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('полный разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
print('\n===== СВОДКА =====')
for s in svodka:
    print(s)
