# -*- coding: utf-8 -*-
"""Что живёт на /obzvon/meyer боевой панели и сколько там данных.

Решение «куда ставить копию» зависит от одного факта: занят ли путь /obzvon/meyer живой
страницей. Если занят и там данные — ставить копию туда значит затенить работающее.
Поэтому сперва замер, а не правка Caddy.
"""
import io
import os
import re
import sqlite3
import urllib.error
import urllib.request

vyhod = []


def pishi(s=''):
    vyhod.append(str(s))
    print(s)


class BezRedirekta(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


op = urllib.request.build_opener(BezRedirekta)


def proba(port, put):
    try:
        o = op.open('http://127.0.0.1:%d%s' % (port, put), timeout=25)
        telo = o.read().decode('utf-8', 'replace')
        zag = re.search(r'<title>(.*?)</title>', telo, re.S)
        return o.status, len(telo), (zag.group(1).strip()[:60] if zag else ''), ''
    except urllib.error.HTTPError as e:
        telo = (e.read() or b'').decode('utf-8', 'replace')
        return e.code, len(telo), telo[:70].replace('\n', ' '), (
            e.headers.get('Location') or '')
    except Exception as e:  # noqa: BLE001
        return 'ОШИБКА', 0, str(e)[:60], ''


pishi('########## ЧТО ОТДАЁТ БОЕВАЯ ПАНЕЛЬ (8012)')
for put in ('/obzvon', '/obzvon/', '/obzvon/meyer', '/obzvon/kc', '/obzvon/centro',
            '/obzvon/centro1', '/obzvon/centro2', '/obzvon/meyer/obzvon'):
    kod, dl, zag, kuda = proba(8012, put)
    pishi('   %-24s -> %-5s %7s байт  %s%s'
          % (put, kod, dl, zag, ('  Location=' + kuda) if kuda else ''))

pishi()
pishi('########## ЧТО ОТДАЁТ КОПИЯ (8016)')
for put in ('/obzvon', '/obzvon/meyer', '/obzvon/centro'):
    kod, dl, zag, kuda = proba(8016, put)
    pishi('   %-24s -> %-5s %7s байт  %s%s'
          % (put, kod, dl, zag, ('  Location=' + kuda) if kuda else ''))

pishi()
pishi('########## РЕЕСТР callbase.BASES И ЕГО ДАННЫЕ')
p = r'C:\centro2\app\services\callbase.py'
t = io.open(p, encoding='utf-8', errors='replace').read()
for i, l in enumerate(t.splitlines(), 1):
    if re.search(r'BASES|DB_|PATH|sqlite|def db|TABLE|таблиц', l):
        pishi('   %4d: %s' % (i, l.strip()[:165]))

pishi()
pishi('########## БАЗА СТАРОГО ОБЗВОНА: ЕСТЬ ЛИ ТАМ MEYER')
kand = [r'C:\seostat\data\callbase.db', r'C:\seostat\data\obzvon.db',
        r'C:\seostat\data\call.db']
m = re.findall(r'["\']([A-Za-z]:\\[^"\']+\.db)["\']', t) + re.findall(
    r'["\']([\w/\\.-]+\.db)["\']', t)
for q in m:
    if q not in kand:
        kand.append(q if os.path.isabs(q) else os.path.join(r'C:\seostat', q))
for q in kand:
    if not os.path.exists(q):
        pishi('   %s — нет' % q)
        continue
    pishi('   %s — ЕСТЬ, %.1f МБ' % (q, os.path.getsize(q) / 1048576.0))
    try:
        c = sqlite3.connect('file:%s?mode=ro' % q, uri=True)
        tabl = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        pishi('      таблицы: %s' % ', '.join(tabl[:14]))
        for tb in tabl:
            kol = [r[1] for r in c.execute('PRAGMA table_info(%s)' % tb)]
            if 'base' in kol or 'division' in kol:
                pole = 'base' if 'base' in kol else 'division'
                raskl = list(c.execute(
                    'SELECT %s, COUNT(*) FROM %s GROUP BY 1 ORDER BY 2 DESC LIMIT 8'
                    % (pole, tb)))
                pishi('      %s.%s: %s' % (tb, pole, raskl))
    except Exception as e:  # noqa: BLE001
        pishi('      прочитать не удалось: %s' % str(e)[:70])

io.open(r'C:\seostat\drop\drop-storage\probe-meyer-put.txt', 'w',
        encoding='utf-8').write('\n'.join(vyhod))
print('\n(отчёт также на дропе: probe-meyer-put.txt)')
