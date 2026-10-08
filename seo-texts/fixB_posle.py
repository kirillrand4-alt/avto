# -*- coding: utf-8 -*-
"""fixB: после выката – только чтение: хвост лога с перезапуска, схема и счётчики базы продаж."""
import io
import os
import sqlite3
import urllib.request

lg = io.open(r'C:\centro2\centro2.log', encoding='utf-8', errors='replace').read()
i = lg.rfind('===== перезапуск: fixB')
hv = lg[i:] if i >= 0 else lg[-3000:]
print('строк лога после перезапуска fixB: %d; Traceback: %d; " 500 ": %d' % (
    hv.count('\n'), hv.count('Traceback'), hv.count(' 500 ')))
print('последний перезапуск в логе:', lg[lg.rfind('===== перезапуск'):][:110].replace('\n', ' '))
s = sqlite3.connect(r'file:C:\centro2\data\centro_sales_meyer1.db?mode=ro', uri=True)
print('zvonok_sobytie:', s.execute('select count(*) from zvonok_sobytie').fetchone()[0],
      '| prichina в state/comment:', ['prichina' in [r[1] for r in s.execute('pragma table_info(%s)' % t)] for t in ('company_state', 'company_comment')])
print('state/comment/log/assign:', [s.execute('select count(*) from %s' % t).fetchone()[0] for t in ('company_state', 'company_comment', 'activity_log', 'company_assignment')])
s.close()
k = sqlite3.connect(r'file:C:\centro2\data\meyer_baza1.db?mode=ro', uri=True)
print('контактов «от продавца» в каталоге:', k.execute("select count(*) from contact where source like 'от продавца%'").fetchone()[0])
k.close()
print('вход:', urllib.request.urlopen('http://127.0.0.1:8016/obzvon-meyer/centro/login', timeout=30).status)
st = io.open(r'C:\centro2\app\templates\centro_stats.html', encoding='utf-8').read()
print('мобильная вёрстка статистики:', 'fixB: на телефоне и планшете' in st, '| замок:', os.path.exists(r'C:\centro2\_zamok.txt'))
