# -*- coding: utf-8 -*-
r"""fixD: откат своей записи по журналу «было → стало» (НЕ запускается сам по себе; только если
владелец/координатор попросит). Возвращает только то, что fixD записал, и только там, где в базе
до сих пор стоит записанное fixD значение (чужие правки после записи не трогаются).

    3s_fixD_otkat.py fixD-zhurnal-<время>.json [--suhoy]
"""
import io
import json
import os
import sqlite3
import sys

KAT = r'C:\centro2\data\meyer_baza1.db'
DROP = r'C:\seostat\drop\drop-storage'
zh = json.load(io.open(os.path.join(DROP, sys.argv[1]), encoding='utf-8'))
SUHOY = '--suhoy' in sys.argv
k = sqlite3.connect(KAT, timeout=60)
n = {'company': 0, 'contact': 0, 'propusk': 0}
with k:
    for z in zh['izmeneniya']:
        if z.get('tablica') == 'company' and 'pole' in z:
            tek = k.execute('select %s from company where inn=?' % z['pole'], (z['inn'],)).fetchone()
            if tek and (tek[0] or '') == (z['stalo'] or ''):
                if not SUHOY:
                    k.execute('update company set %s=? where inn=?' % z['pole'], (z['bylo'], z['inn']))
                n['company'] += 1
            else:
                n['propusk'] += 1
        elif z.get('tablica') == 'contact':
            tek = k.execute('select chuzhoy_istochnik from contact where id=?', (z['id'],)).fetchone()
            if tek and (tek[0] or '') == (z['stalo'] or ''):
                if not SUHOY:
                    k.execute('update contact set chuzhoy_istochnik=?, chuzhoy_dokaz=NULL where id=?', (z['bylo'], z['id']))
                n['contact'] += 1
            else:
                n['propusk'] += 1
    if not SUHOY:
        k.execute("delete from holding_chlen where gruppa like 'gD-%'")
        k.execute("update holding_chlen set gruppa=substr(gruppa, 12) where gruppa like 'snyato0810-%'")
    if SUHOY:
        raise SystemExit('сухой прогон: ' + json.dumps(n, ensure_ascii=False))
print('откат:', json.dumps(n, ensure_ascii=False))
