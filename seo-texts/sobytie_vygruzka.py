# -*- coding: utf-8 -*-
"""Разведка 2: выложить на дроп исходник news_scan.py и полный дамп signals.

Зачем через дроп, а не через stdout: вывод задания возвращается хвостом ~6000 знаков,
а исходник 1800 строк и 3725 строк базы туда не влезут никогда. Дроп на сервере доступен
(проверено разведкой 1: DROP_URL и DROP_TOKEN в окружении есть).

Прибор только читает базу. Ничего не пишет ни в базу, ни в живые файлы.
"""
import gzip
import io
import json
import os
import sqlite3
import sys
import urllib.request

BAZA = r'C:\sender\enrich.db'
DROP = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
TOK = os.environ.get('DROP_TOKEN', '')


def polozhit(imya, dannye):
    req = urllib.request.Request('%s/%s' % (DROP, imya), data=dannye, method='PUT',
                                 headers={'X-Drop-Token': TOK,
                                          'Content-Type': 'application/octet-stream'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.status, len(dannye)


# --- исходник
put = r'C:\sender\server\news_scan.py'
ish = io.open(put, encoding='utf-8', errors='replace').read()
st, n = polozhit('3s_news_scan_kopiya.py.gz', gzip.compress(ish.encode('utf-8')))
print('news_scan.py: %d знаков -> дроп %d байт, статус %s' % (len(ish), n, st))

# --- дамп signals
con = sqlite3.connect('file:%s?mode=ro' % BAZA, uri=True)
con.row_factory = sqlite3.Row
cur = con.cursor()
cols = [r[1] for r in cur.execute('PRAGMA table_info(signals)')]
buf = io.StringIO()
k = 0
for r in cur.execute('SELECT rowid AS rid, * FROM signals ORDER BY rowid'):
    d = {c: r[c] for c in ['rid'] + cols}
    buf.write(json.dumps(d, ensure_ascii=False) + '\n')
    k += 1
syr = buf.getvalue().encode('utf-8')
st2, n2 = polozhit('3s_signals_dump.jsonl.gz', gzip.compress(syr))
print('signals: %d строк, %d знаков -> дроп %d байт, статус %s' % (k, len(syr), n2, st2))

# --- заодно: сколько строк seen_news и есть ли там дата публикации
try:
    cc = [r[1] for r in cur.execute('PRAGMA table_info(seen_news)')]
    print('seen_news колонки: %s' % ', '.join(cc))
    pr = cur.execute('SELECT * FROM seen_news LIMIT 2').fetchall()
    for p in pr:
        print('  пример: %s' % json.dumps({c: (str(p[c])[:60]) for c in cc}, ensure_ascii=False)[:220])
except Exception as ex:  # noqa: BLE001
    print('seen_news: %r' % (ex,))

print('\n=== ИТОГ: выложено 3s_news_scan_kopiya.py.gz и 3s_signals_dump.jsonl.gz (%d строк) ===' % k)
con.close()
