# -*- coding: utf-8 -*-
"""fixM: только чтение. Где в базах панели Meyer лежат строки со словом «продав» (таблица, колонка, число, примеры)."""
import os
import sqlite3
for imya in ('meyer_baza1.db', 'centro_sales_meyer1.db'):
    p = os.path.join(r'C:\centro2\data', imya)
    c = sqlite3.connect('file:%s?mode=ro' % p, uri=True)
    print('=====', imya)
    for (t,) in c.execute("select name from sqlite_master where type='table'"):
        try:
            kol = [r[1] for r in c.execute('pragma table_info("%s")' % t)]
        except Exception as e:
            continue
        for k in kol:
            try:
                n = c.execute('select count(*) from "%s" where cast("%s" as text) like ?' % (t, k), ('%продав%',)).fetchone()[0]
            except Exception:
                continue
            if n:
                pr = c.execute('select distinct substr(cast("%s" as text), 1, 160) from "%s" where cast("%s" as text) like ? limit 6' % (k, t, k), ('%продав%',)).fetchall()
                # маскируем цифры (номера)
                import re
                pr = [re.sub(r'\d{5,}', '<N>', x[0]) for x in pr]
                print('%s.%s: %d  %s' % (t, k, n, ' || '.join(pr)))
    c.close()
