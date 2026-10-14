# -*- coding: utf-8 -*-
r"""fixT: компании панели с успешной сделкой Meyer («Meyer: клиент» / «Meyer: успешное привлечение», fixS) – кто это,
какие сделки Meyer у них в выгрузке 09.10, у какого менеджера, есть ли действия менеджеров. Только чтение.

    python3 zapusk_na_servere.py fixT_uspeshnye.py
"""
import json
import os
import sqlite3

KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item')


def ro(put):
    k = sqlite3.connect('file:%s?mode=ro' % put, uri=True, timeout=30)
    k.row_factory = sqlite3.Row
    return k


kat, s = ro(KAT), ro(SALES)
nazn = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
rows = kat.execute("SELECT inn, predpriyatie AS name, bitrix_metki, bitrix_metki_podrobno FROM company "
                   "WHERE bitrix_meyer_uspeshno=1 ORDER BY bitrix_metki").fetchall()
print('с успешной сделкой Meyer: %d' % len(rows))
import sys  # noqa: E402
if '--kratko' in sys.argv:
    for r in rows:
        print('%s | %s | %s | %s' % (r['inn'], r['name'], nazn.get(r['inn']), r['bitrix_metki']))
    raise SystemExit(0)
for r in rows:
    d = {}
    for t in DEYSTVIYA:
        try:
            n = s.execute('SELECT COUNT(*) FROM %s WHERE inn=?' % t, (r['inn'],)).fetchone()[0]
        except sqlite3.OperationalError:
            continue
        if n:
            d[t] = n
    print('\n%s | %s | %s | метки: %s | действия: %s' % (r['inn'], r['name'], nazn.get(r['inn']), r['bitrix_metki'], d or 'нет'))
    print('   ' + str(r['bitrix_metki_podrobno'])[:700].replace('\n', ' / '))


# описание компаний: заполненность по базам и примеры со скриншота владельца (14.10)
kol = [x[1] for x in kat.execute('PRAGMA table_info(company)')]
print('\nколонки описания:', [c for c in kol if any(z in c for z in ('opis', 'produk', 'pasport', 'otrasl', 'baza', 'import'))])
bk = 'baza' if 'baza' in kol else next((c for c in kol if 'baz' in c), None)
for c in ('opisanie', 'produkciya', 'pasport_syrye'):
    if c in kol:
        q = 'SELECT %s, COUNT(*), SUM(CASE WHEN COALESCE(TRIM(%s),"")="" THEN 1 ELSE 0 END) FROM company GROUP BY 1' % (bk, c)
        print('пустое %s по базам (база, всего, пусто):' % c, kat.execute(q).fetchall() if bk else '-')
for inn in ('6162088948', '1650298682', '5514001322', '4223119624'):
    r = kat.execute('SELECT * FROM company WHERE inn=?', (inn,)).fetchone()
    if r:
        r = dict(r)
        print('\n%s %s: база=%s' % (inn, r.get('predpriyatie'), r.get(bk)))
        for c in ('opisanie', 'produkciya', 'pasport_syrye', 'pasport_oborudovanie', 'otrasl', 'meyer_verdikt_pochemu'):
            print('   %s: %s' % (c, str(r.get(c))[:160]))
