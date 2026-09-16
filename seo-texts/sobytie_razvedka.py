# -*- coding: utf-8 -*-
"""Разведка 1: откуда берётся `ts` у signals и что вообще есть про дату.

Прибор ничего не пишет. Только читает живой код `C:\\sender\\server\\news_scan.py`
и живую базу `C:\\sender\\enrich.db`.

Порядок печати сделан под то, что вывод возвращается ХВОСТОМ: сперва длинные куски
кода, в самом конце - короткий итог, который точно доедет.
"""
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')

BAZA = r'C:\sender\enrich.db'
itog = []


def vyvod(s=''):
    print(s)


# ---------------------------------------------------------------- код news_scan
try:
    import news_scan as NS  # noqa: E402
    put = NS.__file__
except Exception as ex:  # noqa: BLE001
    put = r'C:\sender\server\news_scan.py'
    vyvod('import news_scan не прошёл: %r (читаю файл напрямую)' % (ex,))

ish = io.open(put, encoding='utf-8', errors='replace').read().split('\n')
vyvod('news_scan = %s, строк %d' % (put, len(ish)))


def sovpadeniya(shablon, zag, limit=40, shirina=105):
    rx = re.compile(shablon)
    nayd = [(i + 1, l.strip()) for i, l in enumerate(ish) if rx.search(l)]
    vyvod('\n##### %s : совпадений %d' % (zag, len(nayd)))
    for n, l in nayd[:limit]:
        vyvod('%5d| %s' % (n, l[:shirina]))
    return nayd


sovpadeniya(r'signals', 'слово signals в коде')
sig_ts = sovpadeniya(r"""["']ts["']|\bts\s*=|\bts\b\s*:""", 'слово ts в коде')
sovpadeniya(r'hotness', 'hotness в коде', limit=25)
sovpadeniya(r'pubDate|published|pub_date|updated|entry\.|feedparser|email\.utils|parsedate',
            'даты RSS в коде', limit=30)

# тело функции, которая пишет signals
nachalo = None
for i, l in enumerate(ish):
    if re.search(r'INSERT\s+INTO\s+signals|INSERT OR (REPLACE|IGNORE) INTO signals', l, re.I):
        j = i
        while j >= 0 and not ish[j].startswith('def '):
            j -= 1
        nachalo = j
        break
if nachalo is not None:
    konec = nachalo + 1
    while konec < len(ish) and not (ish[konec].startswith('def ') or ish[konec].startswith('class ')):
        konec += 1
    vyvod('\n##### ФУНКЦИЯ ЗАПИСИ signals: строки %d-%d' % (nachalo + 1, konec))
    for n in range(nachalo, min(konec, nachalo + 90)):
        vyvod('%5d| %s' % (n + 1, ish[n][:115]))
else:
    vyvod('\n##### INSERT INTO signals в news_scan НЕ НАЙДЕН')

# ---------------------------------------------------------------- база
con = sqlite3.connect('file:%s?mode=ro' % BAZA, uri=True)
cur = con.cursor()
cols = [r[1] for r in cur.execute('PRAGMA table_info(signals)')]
vyvod('\n##### signals колонки: %s' % ', '.join(cols))
vsego = cur.execute('SELECT COUNT(*) FROM signals').fetchone()[0]
pusto = cur.execute("SELECT COUNT(*) FROM signals WHERE ts IS NULL OR TRIM(ts)=''").fetchone()[0]
itog.append('signals строк %d, ts пусто %d (%.1f%%)' % (vsego, pusto, 100.0 * pusto / max(vsego, 1)))

# форматы непустого ts
vidy = {}
primery = {}
for (t,) in cur.execute("SELECT ts FROM signals WHERE ts IS NOT NULL AND TRIM(ts)<>''"):
    t = t.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}T', t):
        v = 'ISO с временем'
    elif re.match(r'^\d{4}-\d{2}-\d{2}$', t):
        v = 'ISO дата'
    elif re.match(r'^[A-Za-z]{3},\s*\d{1,2}\s+[A-Za-z]{3}\s+\d{4}', t):
        v = 'RSS RFC-822'
    elif re.match(r'^\d{9,13}$', t):
        v = 'epoch'
    else:
        v = 'прочее'
    vidy[v] = vidy.get(v, 0) + 1
    primery.setdefault(v, t[:40])
vyvod('\n##### форматы непустого ts')
for v, n in sorted(vidy.items(), key=lambda x: -x[1]):
    vyvod('  %-16s %5d   пример: %s' % (v, n, primery[v]))
itog.append('форматы ts: ' + ' · '.join('%s %d' % (v, n) for v, n in sorted(vidy.items(), key=lambda x: -x[1])))

# заполненность ts по источникам
vyvod('\n##### ts по источникам (топ-18 по числу строк)')
rows = cur.execute("""SELECT source, COUNT(*) n,
                             SUM(CASE WHEN ts IS NULL OR TRIM(ts)='' THEN 1 ELSE 0 END) bez
                      FROM signals GROUP BY source ORDER BY n DESC LIMIT 18""").fetchall()
for s, n, bez in rows:
    vyvod('  %-28s всего %5d  без ts %5d  (%3.0f%%)' % ((s or 'NULL')[:28], n, bez, 100.0 * bez / n))

# updated_at
try:
    uz = cur.execute("SELECT COUNT(*) FROM signals WHERE updated_at IS NOT NULL AND TRIM(updated_at)<>''").fetchone()[0]
    pr = cur.execute("SELECT updated_at FROM signals WHERE updated_at IS NOT NULL AND TRIM(updated_at)<>'' LIMIT 3").fetchall()
    vyvod('\nupdated_at заполнен у %d строк, примеры: %s' % (uz, [p[0] for p in pr]))
    itog.append('updated_at заполнен у %d из %d' % (uz, vsego))
except Exception as ex:  # noqa: BLE001
    vyvod('updated_at: %r' % (ex,))

# есть ли ещё таблицы с датами
vyvod('\n##### таблицы базы и их «датные» колонки')
tabl = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
for t in tabl:
    try:
        n = cur.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        cc = [r[1] for r in cur.execute('PRAGMA table_info("%s")' % t)]
        dd = [c for c in cc if re.search(r'date|ts|time|dat', c, re.I)]
        if n:
            vyvod('  %-24s строк %7d  датные: %s' % (t[:24], n, ', '.join(dd) or '-'))
    except Exception:  # noqa: BLE001
        pass

# сколько строк с датой в тексте what
tekst_data = cur.execute(r"""SELECT COUNT(*) FROM signals WHERE what IS NOT NULL AND (
        what GLOB '*20[2-3][0-9]*' )""").fetchone()[0]
itog.append('в тексте what встречается год 20xx у %d строк' % tekst_data)

vyvod('\nDROP_URL в окружении сервера: %s, DROP_TOKEN: %s'
      % (bool(os.environ.get('DROP_URL')), bool(os.environ.get('DROP_TOKEN'))))

vyvod('\n=========== ИТОГ ===========')
for s in itog:
    vyvod('* ' + s)
vyvod('строк ts-совпадений в коде: %d' % len(sig_ts))
con.close()
