# -*- coding: utf-8 -*-
"""Разведка 3: КТО ещё пишет signals и что делает add_signal с датой при повторе.

Вопрос конкретный: `news_scan` кладёт `ts=rec['published']`, но у 2848 строк пусто.
Надо отделить две причины, они чинятся по-разному:
  1) коллектор не дал дату (в item `pubDate` пустой изначально);
  2) дата была, но её ЗАТЁРЛИ при повторной записи того же сигнала.
Вторая версия проверяется только исходником `enrich_db.add_signal`.

Прибор только читает.
"""
import inspect
import io
import os
import re
import sqlite3
import sys

sys.path.insert(0, r'C:\sender\server')
SRV = r'C:\sender\server'

# --- кто зовёт add_signal
print('##### вызовы add_signal по модулям сервера')
for f in sorted(os.listdir(SRV)):
    if not f.endswith('.py'):
        continue
    try:
        t = io.open(os.path.join(SRV, f), encoding='utf-8', errors='replace').read()
    except Exception:  # noqa: BLE001
        continue
    for i, l in enumerate(t.split('\n')):
        if 'add_signal' in l:
            print('  %-24s %5d| %s' % (f[:24], i + 1, l.strip()[:90]))

# --- исходник add_signal
try:
    import enrich_db as EDB  # noqa: E402
    src = inspect.getsource(EDB.EnrichDB.add_signal)
    print('\n##### enrich_db.EnrichDB.add_signal (%s)' % EDB.__file__)
    for l in src.split('\n')[:70]:
        print('   ' + l[:115])
except Exception as ex:  # noqa: BLE001
    print('add_signal не прочитан: %r' % (ex,))

# --- что в базе у источников, которые ДОЛЖНЫ иметь дату (hh)
con = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True)
cur = con.cursor()
print('\n##### источники, где коллектор дату ДАЁТ (hh.ru, ЕИС план 223-ФЗ, rss-доноры)')
for s in ('hh.ru', 'ЕИС план 223-ФЗ', 'ЕИС', 'ВКонтакте', 'ФРП'):
    r = cur.execute("SELECT COUNT(*), SUM(CASE WHEN ts IS NULL OR TRIM(ts)='' THEN 1 ELSE 0 END) "
                    'FROM signals WHERE source=?', (s,)).fetchone()
    print('  %-18s всего %5d  без ts %s' % (s, r[0] or 0, r[1]))

# --- дублирование: один и тот же source_url несколько раз?
d = cur.execute("""SELECT COUNT(*) FROM (SELECT source_url FROM signals
                   WHERE source_url<>'' GROUP BY source_url HAVING COUNT(*)>1)""").fetchone()[0]
print('\nссылок, встречающихся в signals больше одного раза: %d' % d)
par = cur.execute("""SELECT COUNT(*) FROM (SELECT inn, source_url FROM signals
                     WHERE source_url<>'' GROUP BY inn, source_url HAVING COUNT(*)>1)""").fetchone()[0]
print('пар (инн, ссылка) с повтором: %d' % par)

print('\n=== ИТОГ разведки 3 ===')
con.close()
