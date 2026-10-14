# -*- coding: utf-8 -*-
r"""fixY: какие результаты звонка есть в панели Meyer и сколько их уже отмечено – для интеграции с Битриксом. Только чтение.

    python3 zapusk_na_servere.py fixY_razvedka.py
"""
import io
import os
import re
import sqlite3

APP = r'C:\centro2\app'
for f in (r'api\routes_centro_sales.py', r'services\centro_sales.py'):
    t = io.open(os.path.join(APP, f), encoding='utf-8').read().splitlines()
    for i, s in enumerate(t, 1):
        if re.search(r'(RESULT|ISHOD|ИСХОД|call_result|STATUS)\w*\s*=\s*[\[\(\{]', s) or re.search(r'"(Интерес|Перезвонить|Отказ|Не дозвонился|Нецелев)', s):
            print('%s:%d: %s' % (f, i, s.strip()[:220]))
s = sqlite3.connect('file:%s?mode=ro' % os.path.join(r'C:\centro2\data', 'centro_sales_meyer1.db'), uri=True)
print('\ncompany_state.status:', s.execute('SELECT status, COUNT(*) FROM company_state GROUP BY 1 ORDER BY 2 DESC').fetchall())
print('company_state.call_result:', s.execute('SELECT call_result, COUNT(*) FROM company_state GROUP BY 1 ORDER BY 2 DESC').fetchall())
print('zvonok_sobytie.vid:', s.execute('SELECT vid, COUNT(*) FROM zvonok_sobytie GROUP BY 1 ORDER BY 2 DESC').fetchall())
t = io.open(os.path.join(APP, r'services\centro_sales.py'), encoding='utf-8').read().splitlines()
print('\n'.join('%d: %s' % (i, t[i - 1]) for i in range(25, 80)))
