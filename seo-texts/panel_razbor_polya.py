# -*- coding: utf-8 -*-
"""Поля строки очереди, разметка карточки вокруг верха и списка, редирект после сохранения.

Нужно, чтобы:
  * в списке показать то, что реально есть у строки (а не угаданные имена полей);
  * знать, куда ведёт «Сохранить»: если после сохранения панель уходит на /centro без
    inn, то с новым режимом продавец окажется в списке — это надо знать заранее;
  * поставить ссылку «← к списку» в верх карточки, не ломая разметку.
"""
import io
import os
import re
import subprocess
import sys

VENV = r'C:\seostat\.venv\Scripts\python.exe'
KOREN = r'C:\centro2'
OTCHET = r'C:\seostat\drop\drop-storage\razbor-polya.txt'

if '--vnutri' not in sys.argv:
    r = subprocess.run([VENV, os.path.abspath(__file__), '--vnutri'], capture_output=True,
                       timeout=900, cwd=KOREN, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-1500:])
    if r.returncode:
        sys.stdout.write(r.stderr.decode('utf-8', 'replace')[-2500:])
    raise SystemExit(0)

sys.path.insert(0, KOREN)
import zapusk  # noqa: E402,F401 — кладёт .env копии в окружение (как у сервера)
import logging  # noqa: E402
import warnings  # noqa: E402
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)
from app.api import routes_centro_sales as rcs  # noqa: E402

vyhod = []


def pishi(s=''):
    vyhod.append(str(s))


companies, version, db_info = rcs._source_companies()
pishi('########## ПОЛЯ СТРОКИ ОЧЕРЕДИ (_source_companies), строк %d' % len(companies))
c0 = next((c for c in companies if c.get('vyruchka_rub') or c.get('revenue')), companies[0])
for k in sorted(c0):
    v = c0[k]
    pishi('   %-26s %s' % (k, repr(v)[:110]))

C = os.path.join(KOREN, 'app', 'templates', 'centro.html')
ct = io.open(C, encoding='utf-8').read().splitlines()
for a, b, zag in ((100, 140, 'шапка фильтров (начало формы)'),
                  (196, 250, 'верх карточки'),
                  (574, 605, 'список очереди внизу карточки'),
                  (895, 920, 'конец файла')):
    pishi()
    pishi('########## centro.html %d-%d: %s' % (a, b, zag))
    for i in range(a - 1, min(b, len(ct))):
        pishi('   %4d: %s' % (i + 1, ct[i].rstrip()[:180]))

RCS = os.path.join(KOREN, 'app', 'api', 'routes_centro_sales.py')
t = io.open(RCS, encoding='utf-8').read().splitlines()
nach = next(i for i, l in enumerate(t) if '@router.post("/centro/save"' in l)
pishi()
pishi('########## /centro/save')
for j in range(nach, min(len(t), nach + 70)):
    pishi('   %4d: %s' % (j + 1, t[j].rstrip()[:170]))
    if j > nach + 3 and t[j].startswith('@router.'):
        break
# все RedirectResponse на /centro — куда возвращают
pishi()
pishi('########## ВСЕ РЕДИРЕКТЫ НА /centro')
for i, l in enumerate(t, 1):
    if 'RedirectResponse' in l or 'Location' in l:
        pishi('   %4d: %s' % (i, l.strip()[:170]))

io.open(OTCHET, 'w', encoding='utf-8').write('\n'.join(vyhod))
print('разбор: %s (%d строк)' % (OTCHET, len(vyhod)))
