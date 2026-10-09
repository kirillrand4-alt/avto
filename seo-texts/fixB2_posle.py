# -*- coding: utf-8 -*-
"""fixB2: после выката – только чтение: лог с перезапуска, вход, нет ли следов «номера ЛПР»."""
import io
import sqlite3
import urllib.request
lg = io.open(r'C:\centro2\centro2.log', encoding='utf-8', errors='replace').read()
i = lg.rfind('===== перезапуск')
hv = lg[i:]
print('последний перезапуск:', hv[:90].replace('\n', ' '))
print('строк лога после него: %d; Traceback: %d; " 500 ": %d' % (hv.count('\n'), hv.count('Traceback'), hv.count(' 500 ')))
s = sqlite3.connect(r'file:C:\centro2\data\centro_sales_meyer1.db?mode=ro', uri=True)
print('событий lpr_nomer: %d; ne_dozvonilsya: %d' % tuple(
    s.execute("select count(*) from zvonok_sobytie where vid=?", (v,)).fetchone()[0] for v in ('lpr_nomer', 'ne_dozvonilsya')))
s.close()
print('вход:', urllib.request.urlopen('http://127.0.0.1:8016/obzvon-meyer/centro/login', timeout=30).status)
