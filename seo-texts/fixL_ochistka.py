# -*- coding: utf-8 -*-
r"""fixL (15.10): убрать из панели следы ТЕСТОВ «Завести лид в Битрикс» (владелец: «убери информацию из панели о тестах»).

Тесты шли только на компании АО «Птицефабрика „Тульская“» (ИНН 7130001590, meyer9): лид 379905 (агент, уже откачен) и
379918 (проба владельца под meyer9). Убираются ВСЕ строки базы продаж по 7130001590 (статус, комментарии, звонки, журнал,
скрытие, записи о лидах) и строки bitrix_lid тестовых лидов – компания снова «Новый», без «лид уже заводили».
Строки сначала пишутся в журнал на дроп, копия базы – C:\centro2\_bekap\fixL-ochistka-<время>\. Каталог не трогается.

    python3 zapusk_na_servere.py fixL_ochistka.py              # показать, что будет удалено
    python3 zapusk_na_servere.py fixL_ochistka.py --primenit   # удалить
"""
import io
import json
import os
import sqlite3
import sys
import time

SALES = r'C:\centro2\data\centro_sales_meyer1.db'
INN = '7130001590'
TEST_LIDY = ('379905', '379918')
TABLICY = ('company_state', 'company_comment', 'zvonok_sobytie', 'activity_log', 'hidden_item', 'bitrix_lid')
VREMYA = time.strftime('%Y%m%d-%H%M%S')

k = sqlite3.connect(SALES, timeout=30)
k.row_factory = sqlite3.Row
naydeno = {}
for t in TABLICY:
    try:
        kol = [r[1] for r in k.execute('PRAGMA table_info(%s)' % t)]
    except sqlite3.OperationalError:
        continue
    if not kol:
        continue
    usl, par = [], []
    if 'inn' in kol:
        usl.append('inn=?')
        par.append(INN)
    if t == 'bitrix_lid':
        lk = next((c for c in kol if c in ('lead_id', 'lid_id', 'bitrix_id')), None)
        if lk:
            usl.append('CAST(%s AS TEXT) IN (%s)' % (lk, ','.join('?' * len(TEST_LIDY))))
            par += list(TEST_LIDY)
    if not usl:
        continue
    rows = [dict(r) for r in k.execute('SELECT rowid AS _rowid, * FROM %s WHERE %s' % (t, ' OR '.join(usl)), par)]
    if rows:
        naydeno[t] = rows
for t, rows in naydeno.items():
    print('%s: %d' % (t, len(rows)))
    for r in rows:
        print('   ' + json.dumps({x: (str(v)[:80] if v is not None else None) for x, v in r.items()
                                  if x not in ('nomer', 'nomer_10', 'telefon', 'phone')}, ensure_ascii=False)[:400])
if '--primenit' not in sys.argv:
    print('\nПОКАЗ: ничего не удалено')
    raise SystemExit(0)
papka = os.path.join(r'C:\centro2\_bekap', 'fixL-ochistka-' + VREMYA)
os.makedirs(papka, exist_ok=True)
b = sqlite3.connect(os.path.join(papka, 'centro_sales_meyer1.db'))
k.backup(b)
b.close()
io.open(os.path.join(r'C:\seostat\drop\drop-storage', 'fixL-ochistka-zhurnal-%s.json' % VREMYA), 'w', encoding='utf-8').write(
    json.dumps(naydeno, ensure_ascii=False, indent=0, default=str))
k.execute('BEGIN IMMEDIATE')
try:
    for t, rows in naydeno.items():
        for r in rows:
            k.execute('DELETE FROM %s WHERE rowid=?' % t, (r['_rowid'],))
    k.execute('COMMIT')
except Exception:
    k.execute('ROLLBACK')
    raise
ost = {t: k.execute('SELECT COUNT(*) FROM %s WHERE inn=?' % t, (INN,)).fetchone()[0] for t in naydeno}
print('\nУДАЛЕНО: %s; осталось по %s: %s; журнал fixL-ochistka-zhurnal-%s.json; копия базы %s' % (
    {t: len(r) for t, r in naydeno.items()}, INN, ost, VREMYA, papka))
