# -*- coding: utf-8 -*-
r"""fixDR (16.11): панель Meyer – разведка «домашних регионов», только чтение.

Правило владельца 13.10: «у кого какой город – другим этот город не отдавать (область/край)»: Алтайский край –
только барнаульским, Краснодарский край – только краснодарским, Воронежская область – только воронежским; прочие
регионы – любому. Владелец 16.11: «проверь, чтобы у тех, кто из Алтайского края, не было краснодарских/воронежских,
перекинь их в свои регионы для всех». Печатает нарушения: регион, у кого, есть ли работа менеджера, холдинги.

    python3 zapusk_na_servere.py fixDR_razvedka.py
"""
import collections
import os
import sqlite3

KOREN = r'C:\centro2'
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')

s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
lyudi = {u: (f, g) for u, f, g in s.execute("SELECT username, fio, COALESCE(gorod,'') FROM users WHERE role='sales' AND is_active=1")}
print('продавцы:', {u: '%s (%s)' % x for u, x in sorted(lyudi.items())})
vlad = dict(s.execute('SELECT inn, username FROM company_assignment').fetchall())
region = dict(k.execute('SELECT inn, region FROM company').fetchall())
nazv = dict(k.execute('SELECT inn, predpriyatie FROM company').fetchall())
hold = {str(i): str(g) for i, g in k.execute('SELECT inn, gruppa FROM holding_chlen') if g}
print('написания регионов (похожие):', sorted({r for r in region.values() if r and any(x in r for x in ('Алтай', 'Краснодар', 'Воронеж'))}))
DOM = {'Алтайский край': 'Барнаул', 'Краснодарский край': 'Краснодар', 'Воронежская область': 'Воронеж'}
status = dict(((i, u), r) for i, u, r in s.execute("SELECT inn, username, COALESCE(call_result,'new') FROM company_state"))
komm = collections.Counter((i, u) for i, u in s.execute('SELECT inn, username FROM company_comment'))
try:
    sob = collections.Counter((i, u) for i, u in s.execute('SELECT inn, state_user FROM zvonok_sobytie'))
except sqlite3.OperationalError:
    sob = collections.Counter()

print('\nпо домашним регионам: кому сейчас закреплены (город менеджера)')
for r, g in DOM.items():
    c = collections.Counter('%s/%s' % (lyudi.get(vlad[i], ('?', '?'))[1], lyudi.get(vlad[i], ('?', '?'))[0]) for i in vlad if region.get(i) == r)
    print('  %s (дом %s): %s' % (r, g, dict(c)))

nar = []
for i, u in vlad.items():
    r = region.get(i)
    if r in DOM and lyudi.get(u, ('', ''))[1] != DOM[r]:
        rab = status.get((i, u), 'new')
        nar.append((r, u, i, rab, komm[(i, u)], sob[(i, u)], hold.get(i)))
print('\nНАРУШЕНИЙ: %d' % len(nar))
print('по (регион, у кого, статус):', dict(collections.Counter((r, lyudi[u][0], 'со статусом' if rab != 'new' else 'в очереди')
                                                             for r, u, i, rab, kk, ss, h in nar)))
print('из них с комментариями/недозвонами менеджера: %d' % sum(1 for x in nar if x[4] or x[5]))
print('из компаний Волкова (fixVR): %d' % s.execute('SELECT COUNT(*) FROM company_assignment WHERE vladelec_do_fixVR IS NOT NULL AND inn IN (%s)'
                                                     % ','.join('?' * len(nar)), [x[2] for x in nar]).fetchone()[0] if nar else 0)
for r, u, i, rab, kk, ss, h in sorted(nar)[:60]:
    print('  %-20s %-17s %s %-34s статус=%s комм=%d недозв=%d холдинг=%s' % (r, lyudi[u][0], i, (nazv.get(i) or '')[:34], rab, kk, ss, h or '-'))
# холдинги, где нарушитель в группе с компаниями других регионов
sm = collections.defaultdict(list)
for i, g in hold.items():
    if i in vlad:
        sm[g].append(i)
for g in sorted({x[6] for x in nar if x[6]}):
    print('  холдинг %s: %s' % (g, [(i, region.get(i), lyudi.get(vlad[i], ('?',))[0]) for i in sm[g]]))
print('\nзакреплено сейчас:', {lyudi[u][0]: n for u, n in s.execute('SELECT username, COUNT(*) FROM company_assignment GROUP BY 1') if u in lyudi})
