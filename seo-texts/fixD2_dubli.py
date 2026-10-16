# -*- coding: utf-8 -*-
r"""fixD2 (16.10): что менеджеры отметили «Дубль – уже работают» – кто, когда, с какой причиной/комментарием, и что по
компании в Битриксе (метки fixS: Meyer активная / провалено / клиент, сделки КЦ/СЦ в работе). Только чтение.

    python3 zapusk_na_servere.py fixD2_dubli.py
"""
import os
import sqlite3

D = r'C:\centro2\data'
s = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'centro_sales_meyer1.db'), uri=True)
s.row_factory = sqlite3.Row
k = sqlite3.connect('file:%s?mode=ro' % os.path.join(D, 'meyer_baza1.db'), uri=True)
k.row_factory = sqlite3.Row
fio = dict(s.execute("SELECT username, COALESCE(fio,'') FROM users"))
rows = s.execute("SELECT * FROM company_state WHERE call_result='dubl' ORDER BY updated_at").fetchall()
print('«Дубль – уже работают»: %d' % len(rows))
for r in rows:
    c = k.execute("SELECT predpriyatie, bitrix_metki, bitrix_metki_podrobno, bitrix_v_rabote FROM company WHERE inn=?", (r['inn'],)).fetchone()
    kom = s.execute("SELECT body, prichina FROM company_comment WHERE inn=? ORDER BY created_at DESC LIMIT 2", (r['inn'],)).fetchall()
    print('\n%s | %s | %s (%s) | %s | причина: %s' % (r['inn'], c['predpriyatie'] if c else '?', fio.get(r['username'], ''), r['username'],
                                                 str(r['updated_at'])[:16], r['prichina']))
    print('   метки Битрикса: %s; в работе (fixH): %s' % (c['bitrix_metki'] if c else '', c['bitrix_v_rabote'] if c else ''))
    print('   подробно: %s' % (str(c['bitrix_metki_podrobno'])[:420] if c else ''))
    for x in kom:
        print('   комментарий: %s | причина: %s' % (str(x['body'])[:200].replace('\n', ' '), x['prichina']))
