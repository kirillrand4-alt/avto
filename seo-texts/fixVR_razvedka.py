# -*- coding: utf-8 -*-
r"""fixVR (02.11): разведка перед раздачей компаний уволившегося Волкова (панель Meyer) – только чтение.

Владелец 02.11: «волков, те что были у него, раскидай равномерно во "вся очередь" остальным» / «он уволился».
Печатает: пользователей, назначения Волкова по статусам, скрытые, регионы, холдинги, колонки назначения и код
centro_sales.reassign (чтобы раздача повторяла логику панели). Ничего не пишет.

    python3 zapusk_na_servere.py fixVR_razvedka.py
"""
import collections
import io
import os
import re
import sqlite3

KOREN = r'C:\centro2'
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')

s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True, timeout=30)
s.row_factory = sqlite3.Row
ukol = [r[1] for r in s.execute('PRAGMA table_info(users)')]
print('users:', ukol)
for r in s.execute('SELECT * FROM users ORDER BY username'):
    r = dict(r)
    print('  %-22s роль=%-6s акт=%s %s %s' % (r['username'], r.get('role'), r.get('is_active'), r.get('fio') or '',
                                                r.get('gorod') or ''))
vol = [r[0] for r in s.execute("SELECT username FROM users WHERE fio LIKE 'Волков%'")]
print('Волков:', vol)
OT = vol[0]
akol = [r[1] for r in s.execute('PRAGMA table_info(company_assignment)')]
print('company_assignment:', akol)
rows = [dict(r) for r in s.execute('SELECT * FROM company_assignment WHERE username=?', (OT,))]
inn_v = {r['inn'] for r in rows}
print('у %s назначений: %d' % (OT, len(rows)))
sost = {r['inn']: dict(r) for r in s.execute('SELECT * FROM company_state WHERE username=?', (OT,))}
print('статусы:', collections.Counter((sost.get(i) or {}).get('call_result') or 'new' for i in inn_v))
# состояния этих компаний у ДРУГИХ пользователей (если раньше были у кого-то)
print('состояния этих ИНН у других:', collections.Counter(r[0] for r in s.execute(
    'SELECT username FROM company_state WHERE username<>? AND inn IN (SELECT inn FROM company_assignment WHERE username=?)', (OT, OT))))
hkol = [r[1] for r in s.execute('PRAGMA table_info(hidden_item)')]
print('hidden_item:', hkol)
print('скрытия по компаниям Волкова (kind, кто):', collections.Counter((r[0], r[1]) for r in s.execute(
    'SELECT kind, username FROM hidden_item WHERE inn IN (SELECT inn FROM company_assignment WHERE username=?)', (OT,))))
for t in ('company_comment', 'activity_log', 'zvonok_sobytie', 'bitrix_lid'):
    try:
        print('%s по его ИНН: %s' % (t, s.execute('SELECT COUNT(*) FROM %s WHERE inn IN (SELECT inn FROM company_assignment WHERE '
                                                  'username=?)' % t, (OT,)).fetchone()[0]))
    except sqlite3.OperationalError as e:
        print(t, e)
print('ступени у его компаний:', collections.Counter(r.get('stupen_ocheredi') for r in rows))
print('сейчас назначено:', dict(s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1').fetchall()))

k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True, timeout=30)
kkol = [r[1] for r in k.execute('PRAGMA table_info(company)')]
print('\nкаталог company, колонки про холдинг/регион:', [c for c in kkol if re.search(r'hold|grupp|region|gorod|oblast', c)])
q = ','.join('?' * len(inn_v))
if 'region' in kkol:
    print('регионы его компаний:', collections.Counter(r[0] for r in k.execute(
        'SELECT region FROM company WHERE inn IN (%s)' % q, list(inn_v))).most_common(15))
for c in [c for c in kkol if re.search(r'hold|grupp', c)]:
    zn = [r[0] for r in k.execute('SELECT %s FROM company WHERE inn IN (%s)' % (c, q), list(inn_v))]
    print('холдинг-колонка %s: заполнено %d из %d, групп >1: %d' % (
        c, sum(1 for z in zn if z), len(zn), sum(1 for v in collections.Counter(z for z in zn if z).values() if v > 1)))
for t in [r[0] for r in k.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%hold%'")]:
    print('таблица холдингов в каталоге:', t, [r[1] for r in k.execute('PRAGMA table_info(%s)' % t)])

kod = io.open(os.path.join(KOREN, 'app', 'services', 'centro_sales.py'), encoding='utf-8').read().splitlines()
st = next((i for i, l in enumerate(kod) if l.startswith('def reassign')), None)
print('\n--- centro_sales.reassign ---')
if st is not None:
    for l in kod[st:st + 50]:
        print('  ' + l)
        if l.startswith('def ') and l is not kod[st]:
            break
