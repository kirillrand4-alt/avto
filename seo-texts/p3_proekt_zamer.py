# -*- coding: utf-8 -*-
"""ЗАМЕР перед постройкой объекта «проект». Только чтение базы.

Задача: не поверить переданным числам, а перемерить их самой, и выложить на дроп полный
дамп `signals`, чтобы разбор склейки шёл в песочнице, а не заданиями на общем пуле.

Печатаю: список таблиц, колонки signals, счётчики, распределения, длины текстов, примеры.
Числа в КОНЦЕ (вывод возвращается хвостом).
"""
import collections
import io
import json
import os
import sqlite3
import urllib.request

BAZA = r'C:\sender\enrich.db'
VYHOD = r'C:\sender\_ops\3s_signals_dump.json'

con = sqlite3.connect('file:%s?mode=ro' % BAZA.replace('\\', '/'), uri=True)
con.row_factory = sqlite3.Row
cur = con.cursor()

tabl = [r[0] for r in cur.execute(
    "select name from sqlite_master where type='table' order by name")]
print('ТАБЛИЦ: %d' % len(tabl))
print('  ' + ', '.join(tabl))

# ищем всё, что похоже на проект/стадию
pohozhie = [t for t in tabl if any(s in t.lower() for s in
                                   ('proj', 'proekt', 'stage', 'stadi', 'event', 'sobyt'))]
print('ПОХОЖИЕ НА ПРОЕКТ/СТАДИЮ: %s' % (pohozhie or 'НЕТ'))
for t in pohozhie:
    kol = [r[1] for r in cur.execute('pragma table_info(%s)' % t)]
    n = cur.execute('select count(*) from %s' % t).fetchone()[0]
    print('  %s: %d строк, колонки %s' % (t, n, ','.join(kol)))

kol = [r[1] for r in cur.execute('pragma table_info(signals)')]
print('SIGNALS КОЛОНКИ: %s' % ','.join(kol))
n = cur.execute('select count(*) from signals').fetchone()[0]
n_inn = cur.execute("select count(*) from signals where inn is not null and inn<>''"
                    ).fetchone()[0]
n_r_inn = cur.execute("select count(distinct inn) from signals where inn is not null "
                      "and inn<>''").fetchone()[0]
print('SIGNALS: строк %d, с ИНН %d, разных ИНН %d' % (n, n_inn, n_r_inn))

for c in ('source', 'event_type', 'hotness', 'inn_conf', 'suspect'):
    if c not in kol:
        continue
    r = cur.execute('select %s, count(*) c from signals group by 1 order by c desc limit 12'
                    % c).fetchall()
    print('  %s: %s' % (c, ' | '.join('%s=%d' % ((x[0] if x[0] not in (None, '') else '∅'),
                                                 x[1]) for x in r)))
    rr = cur.execute('select count(distinct %s) from signals' % c).fetchone()[0]
    print('    разных значений: %d' % rr)

# многосигнальные ИНН
mn = cur.execute("select inn, count(*) c, count(distinct source) s from signals "
                 "where inn is not null and inn<>'' group by inn order by c desc limit 8"
                 ).fetchall()
print('ТОП ИНН ПО ЧИСЛУ СИГНАЛОВ:')
for x in mn:
    print('  %s  сигналов %d  источников %d' % (x[0], x[1], x[2]))
bolshe1 = cur.execute("select count(*) from (select inn from signals where inn is not null "
                      "and inn<>'' group by inn having count(*)>1)").fetchone()[0]
dva_ist = cur.execute("select count(*) from (select inn from signals where inn is not null "
                      "and inn<>'' group by inn having count(distinct source)>1)"
                      ).fetchone()[0]
print('ИНН с >1 сигналом: %d ; ИНН с >1 источником: %d' % (bolshe1, dva_ist))

# длины текстов what и заполненность
dl = [len(r[0] or '') for r in cur.execute('select what from signals')]
dl.sort()
print('ДЛИНА what: пусто %d, медиана %d, p90 %d, max %d'
      % (sum(1 for x in dl if x == 0), dl[len(dl) // 2], dl[int(len(dl) * 0.9)], dl[-1]))
for c in ('ts', 'updated_at', 'sum', 'source_url'):
    if c not in kol:
        continue
    pust = cur.execute("select count(*) from signals where %s is null or %s=''"
                       % (c, c)).fetchone()[0]
    print('  пусто в %s: %d из %d' % (c, pust, n))

pr = cur.execute('select * from signals limit 3').fetchall()
print('ПРИМЕРЫ СТРОК (3):')
for r in pr:
    d = dict(r)
    print('  ' + json.dumps({k: (str(v)[:150] if v is not None else None)
                             for k, v in d.items()}, ensure_ascii=False))

# форматы ts
fm = collections.Counter()
for r in cur.execute("select ts from signals where ts is not null and ts<>'' limit 4000"):
    t = str(r[0])
    if t.isdigit():
        fm['число'] += 1
    elif ',' in t[:5]:
        fm['RSS'] += 1
    elif '-' in t[:5]:
        fm['ISO'] += 1
    else:
        fm['иное:' + t[:12]] += 1
print('ФОРМАТЫ ts: %s' % dict(fm.most_common(6)))

# ДАМП
rows = [dict(r) for r in cur.execute('select rowid as _rid, * from signals')]
with io.open(VYHOD, 'w', encoding='utf-8') as f:
    json.dump(rows, f, ensure_ascii=False)
razmer = os.path.getsize(VYHOD)

vyl = 'не выкладывала'
try:
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request('%s/%s' % (os.environ.get('DROP_URL', '').rstrip('/'),
                                            os.path.basename(VYHOD)),
                                 data=io.open(VYHOD, 'rb').read(), method='PUT',
                                 headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    vyl = op.open(req, timeout=300).read().decode('utf-8', 'replace')[:120]
except Exception as e:  # noqa: BLE001
    vyl = 'НЕ ВЫЛОЖЕНО: %s' % str(e)[:120]

print('\n########## ЧИСЛА')
print('  таблиц в базе                 %5d' % len(tabl))
print('  таблиц про проект/стадию      %5d' % len(pohozhie))
print('  signals строк                 %5d' % n)
print('  с ИНН                         %5d' % n_inn)
print('  разных ИНН                    %5d' % n_r_inn)
print('  ИНН с >1 сигналом             %5d' % bolshe1)
print('  ИНН с >1 источником           %5d' % dva_ist)
print('  дамп байт                  %8d  -> %s' % (razmer, VYHOD))
print('  выложено на дроп: %s' % vyl)
