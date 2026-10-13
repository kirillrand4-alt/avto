# -*- coding: utf-8 -*-
r"""fixR 13.10: только чтение. Итог по номерам Беларуси: ступени очереди «было -> стало» (по журналу
fixR_pereschet и живой базе продаж), по менеджерам, примеры УНП (без номеров), менеджеры не сменились.
Журнал «было/стало» по ступеням (без телефонов) – на дроп: fixR-stupeni-bylo-stalo-<время>.csv.
    python3 zapusk_na_servere.py fixR_otchet.py fixR-pereschet-zhurnal-20261013-190937.json
"""
import collections
import io
import json
import os
import sqlite3
import sys
import time

KOREN = r'C:\centro2'
KAT = os.path.join(KOREN, 'data', 'meyer_baza1.db')
SALES = os.path.join(KOREN, 'data', 'centro_sales_meyer1.db')
DROP = r'C:\seostat\drop\drop-storage'
STUPEN = {4: 800, 3: 600, 2: 400, 1: 200, 0: 0, None: None}
zh = json.load(io.open(os.path.join(DROP, sys.argv[1]), encoding='utf-8'))
s = sqlite3.connect('file:%s?mode=ro' % SALES, uri=True)
s.row_factory = sqlite3.Row
nazn = {r['inn']: dict(r) for r in s.execute('SELECT inn, username, stupen_ocheredi, assignment_score FROM company_assignment')}
k = sqlite3.connect('file:%s?mode=ro' % KAT, uri=True)
k.row_factory = sqlite3.Row
komp = {r['inn']: dict(r) for r in k.execute('SELECT inn, predpriyatie, strana, lpr_mobilnyy, lpr_s_fio FROM company')}
stroki, po_men, smena = [], collections.defaultdict(collections.Counter), []
for z in zh['kompanii']:
    i = z['inn']
    a = nazn.get(i) or {}
    if a.get('username') != z['menedzher']:
        smena.append((i, z['menedzher'], a.get('username')))
    do, po = STUPEN.get(z['stupen_do']), STUPEN.get(a.get('stupen_ocheredi'))
    by = (z['strana'] == 'Беларусь' or len(i) == 9)
    stroki.append({'inn': i, 'nazv': z['nazvanie'], 'by': by, 'men': a.get('username'), 'do': do, 'po': po,
                   'ball_do': z['ball_do'], 'ball_po': a.get('assignment_score'), 'n_rb': z['nomerov_rb'],
                   'mob_rb': z['lpr_na_mobilnom_rb']})
    if by:
        po_men[a.get('username')]['всего'] += 1
        po_men[a.get('username')]['было %s' % do] += 1
        po_men[a.get('username')]['стало %s' % po] += 1
        if do in (200, 400) and po in (600, 800):
            po_men[a.get('username')]['подъём %s→%s' % (do, po)] += 1
by = [r for r in stroki if r['by']]
ne_by = [r for r in stroki if not r['by']]
print('белорусских компаний: %d; прочих с номерами РБ: %d; менеджер сменился: %d %s' % (len(by), len(ne_by), len(smena), smena[:3]))
podn = [r for r in by if r['do'] in (200, 400) and r['po'] in (600, 800)]
print('БЕЛАРУСЬ: поднялись с 200/400 на 600/800: %d (на 800: %d, на 600: %d); опустились: %d'
      % (len(podn), sum(r['po'] == 800 for r in podn), sum(r['po'] == 600 for r in podn),
         sum(1 for r in by if (r['po'] or 0) < (r['do'] or 0))))
print('всего по ступеням было: %s' % dict(collections.Counter(r['do'] for r in by)))
print('всего по ступеням стало: %s' % dict(collections.Counter(r['po'] for r in by)))
for m in sorted(po_men, key=str):
    c = po_men[m]
    print('  %s: РБ %d; было 800/600/400/200 = %d/%d/%d/%d -> стало %d/%d/%d/%d; подъём %d (→800 %d, →600 %d)' % (
        m, c['всего'], c['было 800'], c['было 600'], c['было 400'], c['было 200'], c['стало 800'], c['стало 600'],
        c['стало 400'], c['стало 200'], c['подъём 400→800'] + c['подъём 400→600'] + c['подъём 200→800'] + c['подъём 200→600'],
        c['подъём 400→800'] + c['подъём 200→800'], c['подъём 400→600'] + c['подъём 200→600']))
print('примеры подъёма (УНП, компания, менеджер, ступень, балл):')
for r in sorted(podn, key=lambda r: -(r['ball_po'] or 0))[:12]:
    print('  %s %s – %s: %s→%s, балл %.1f→%.1f' % (r['inn'], r['nazv'][:40], r['men'], r['do'], r['po'],
                                                 r['ball_do'] or 0, r['ball_po'] or 0))
print('прочие компании с номерами РБ:')
for r in ne_by:
    print('  %s %s – %s: %s→%s (номеров РБ %d, ЛПР на мобильном РБ %d)' % (r['inn'], r['nazv'][:40], r['men'], r['do'], r['po'],
                                                                      r['n_rb'], r['mob_rb']))
VR = time.strftime('%Y%m%d-%H%M%S')
put = os.path.join(DROP, 'fixR-stupeni-bylo-stalo-%s.csv' % VR)
with io.open(put, 'w', encoding='utf-8-sig', newline='') as f:
    f.write('УНП/ИНН;Компания;Беларусь;Менеджер;Ступень было;Ступень стало;Балл было;Балл стало;Номеров РБ;ЛПР на мобильном РБ\n')
    for r in sorted(stroki, key=lambda r: (r['men'] or '', -(r['po'] or 0))):
        f.write('%s;%s;%s;%s;%s;%s;%s;%s;%d;%d\n' % (r['inn'], r['nazv'].replace(';', ','), 'да' if r['by'] else 'нет', r['men'],
                                                   r['do'], r['po'], r['ball_do'], r['ball_po'], r['n_rb'], r['mob_rb']))
print('журнал ступеней: %s' % os.path.basename(put))
# справка к проверке ball-скрипта: у кого список короче CSV (скрытые компании)
try:
    t = [r[0] for r in s.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    if 'hidden_item' in t:
        kol = [r[1] for r in s.execute('PRAGMA table_info(hidden_item)')]
        print('hidden_item: колонки %s' % kol)
        for r in s.execute('SELECT * FROM hidden_item').fetchall():
            d = dict(zip(kol, r))
            inn = str(d.get('inn') or d.get('item_id') or d.get('item_key') or '')
            if inn in nazn and nazn[inn]['username'] == 'meyer4':
                print('  скрыта у meyer4: %s %s (РБ: %s)' % (inn, (komp.get(inn) or {}).get('predpriyatie', '')[:30], len(inn) == 9))
except Exception as e:  # noqa: BLE001
    print('hidden_item: %s' % e)
