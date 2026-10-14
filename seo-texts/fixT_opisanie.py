# -*- coding: utf-8 -*-
r"""fixT: у скольких компаний панели пустое описание (opisanie), и что есть вместо него. Только чтение.

    python3 zapusk_na_servere.py fixT_opisanie.py
"""
import os
import sqlite3

KAT = os.path.join(r'C:\centro2', 'data', 'meyer_baza1.db')
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
pusto = lambda c: "COALESCE(TRIM(%s),'')=''" % c  # noqa: E731
q = lambda w: k.execute('SELECT COUNT(*) FROM company WHERE ' + w).fetchone()[0]  # noqa: E731
print('всего', q('1'))
print('пустое описание', q(pusto('opisanie')))
print('  из них есть продукция', q(pusto('opisanie') + ' AND NOT ' + pusto('produkciya')))
print('  из них есть паспорт (сырьё/оборудование/упаковка/масштаб)', q(pusto('opisanie') + ' AND NOT (' + ' AND '.join(
    pusto(c) for c in ('pasport_syrye', 'pasport_oborudovanie', 'pasport_upakovka', 'pasport_masshtab')) + ')'))
print('  из них ничего, кроме вердикта', q(pusto('opisanie') + ' AND ' + pusto('produkciya') + ' AND ' + ' AND '.join(
    pusto(c) for c in ('pasport_syrye', 'pasport_oborudovanie', 'pasport_upakovka', 'pasport_masshtab'))))
print('есть вердикт «почему»', q('NOT ' + pusto('meyer_verdikt_pochemu')))
