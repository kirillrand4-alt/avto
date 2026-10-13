# -*- coding: utf-8 -*-
r"""fixP: перед удалением не покупателей Meyer (оценка 15 агентов 13.10) – что по ним уже сделали менеджеры.

Только чтение. Вход – дроп fixP-ubrat.json (ИНН, менеджер, причина). Печатает: на месте ли компании и у тех
ли менеджеров, сколько строк действий (статус, комментарий, звонок, журнал, скрытие) и какие статусы/исходы.

    python3 zapusk_na_servere.py fixP_aktivnost.py
"""
import collections
import io
import json
import os
import sqlite3

KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
DEYSTVIYA = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item')


def ro(put):
    k = sqlite3.connect('file:%s?mode=ro' % put, uri=True, timeout=30)
    k.row_factory = sqlite3.Row
    return k


def main():
    ubr = json.load(io.open(os.path.join(DROP, 'fixP-ubrat.json'), encoding='utf-8'))
    inny = [x['inn'] for x in ubr]
    ph = ','.join('?' * len(inny))
    kat, s = ro(KAT), ro(SALES)
    v_kat = {r[0] for r in kat.execute('SELECT inn FROM company WHERE inn IN (%s)' % ph, inny)}
    nazn = {r['inn']: r['username'] if 'username' in r.keys() else r[1]
            for r in s.execute('SELECT * FROM company_assignment WHERE inn IN (%s)' % ph, inny)}
    print('в каталоге %d из %d; назначено %d' % (len(v_kat), len(inny), len(nazn)))
    kol = [r[1] for r in s.execute('PRAGMA table_info(company_assignment)')]
    print('колонки назначения:', kol)
    ne_tot = [x['inn'] for x in ubr if x['inn'] in nazn and str(nazn[x['inn']]) != x['menedzher']]
    print('не у того менеджера:', len(ne_tot), ne_tot[:10])

    est = collections.defaultdict(dict)
    for t in DEYSTVIYA:
        try:
            for inn, c in s.execute('SELECT inn, COUNT(*) FROM %s WHERE inn IN (%s) GROUP BY inn' % (t, ph), inny):
                est[inn][t] = c
        except sqlite3.OperationalError as e:
            print('нет таблицы/колонки', t, e)
    print('\nкомпаний с действиями менеджеров: %d' % len(est))
    for t in DEYSTVIYA:
        print('  %-16s компаний %d' % (t, sum(1 for v in est.values() if t in v)))
    for t in ('company_state', 'zvonok_sobytie', 'company_comment'):
        try:
            kk = [r[1] for r in s.execute('PRAGMA table_info(%s)' % t)]
            print('\n%s колонки: %s' % (t, kk))
            for r in s.execute('SELECT * FROM %s WHERE inn IN (%s) LIMIT 400' % (t, ph), inny):
                d = dict(r)
                for k_ in list(d):
                    if any(z in k_ for z in ('phone', 'telefon', 'nomer', 'tel')):
                        d[k_] = '…'
                txt = json.dumps(d, ensure_ascii=False)
                print('  ' + txt[:330])
        except sqlite3.OperationalError as e:
            print(t, e)


if __name__ == '__main__':
    main()
