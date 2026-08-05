# -*- coding: utf-8 -*-
"""Показать КАЖДОЕ закрытие целиком, чтобы посмотреть глазами, а не поверить счётчику.

Счётчик говорит «13 предприятий, 26 человек». Все три поломки сегодняшней смены нашлись
не счётчиком, а чтением десятка строк выдачи, и это главное число смены — значит его
надо прочесть целиком.

Что показываю по каждому человеку: должность ДОСЛОВНО (а не то, что совпало с моим
шаблоном), номер, источник и кусок текста-основания. Если должность взялась из строки,
где стоит слово «директор» или «менеджер», это будет видно сразу.
"""
import collections
import csv
import glob
import json
import os
import re
import sqlite3

D = r'C:\seostat\drop\drop-storage'
csv.field_size_limit(10 ** 8)
KRUG12 = re.compile(
    r'главн\w+\s+(?:инженер|механик|энергетик|технолог|сварщик|метролог|конструктор)|'
    r'техническ\w+\s+директор|начальник\w*\s+(?:цеха|производств|участка|службы|'
    r'ремонт\w*|энерго\w*)|механик|энергетик|технолог|инженер|КИПиА|АСУ', re.I)
NE_NASH = re.compile(r'персонал|кадр|закупк|снабж|бухгалт|юрист|секретар|маркетинг|'
                     r'продаж|устойчив\w+\s+развити|реклам|пресс', re.I)


def lichnyy(n):
    c = re.sub(r'\D', '', str(n or ''))
    if len(c) == 11 and c[0] in '78':
        c = '7' + c[1:]
    return len(c) == 11 and c.startswith('79')


b = sqlite3.connect('file:C:/seostat/data/p25.db?mode=ro', uri=True)
nashi = {i: n for i, n in b.execute('select inn, coalesce(predpriyatie,"") from company')}
mesta = {i: m for i, m in b.execute('select inn, coalesce(mesto_po_summe,9999) from company')}

KOL_TEL = ('LICHNYY_MOBILNYY', 'telefon', 'znachenie', 'nomer', 'telefon_kak_napisan')
KOL_DOLZH = ('dolzhnost', 'dolzhnost_v_tekste', 'rol_po_kartochke')
KOL_IST = ('pervoistochnik', 'ssylka', 'ssylki', 'chem_podtverzhdena',
           'ssylka_na_kartochku', 'osnovanie', 'chem_dokazana_rol')

lyudi = {}
for p in sorted(glob.glob(os.path.join(D, 'P25-*3S*.csv'))):
    try:
        rows = list(csv.DictReader(open(p, encoding='utf-8-sig'), delimiter=';'))
    except Exception:  # noqa: BLE001
        continue
    for r in rows:
        inn = (r.get('inn') or '').strip()
        if inn not in nashi:
            continue
        dolzh = ' '.join(str(r.get(k) or '') for k in KOL_DOLZH).strip()
        if not KRUG12.search(dolzh) or NE_NASH.search(dolzh):
            continue
        nomer = next((str(r.get(k)) for k in KOL_TEL if lichnyy(r.get(k))), '')
        if not nomer:
            continue
        ist = ' '.join(str(r.get(k) or '') for k in KOL_IST)
        if not re.search(r'https?://|страница на сайте|карточка|реестр|заказчик написал',
                         ist):
            continue
        if 'спорн' in (r.get('uverennost_privyazki') or '').lower():
            continue
        if 'ОБЩИЙ' in (r.get('vid') or '') or 'ЛИНИЯ' in (r.get('vid') or ''):
            continue
        chel = (r.get('chelovek') or r.get('fio') or '').strip()
        k = (inn, chel.lower(), re.sub(r'\D', '', nomer))
        if k in lyudi:
            lyudi[k]['fajlov'] += 1
            continue
        ssyl = next((str(r.get(x)) for x in ('ssylka', 'ssylki', 'ssylka_na_kartochku')
                     if (r.get(x) or '').startswith('http')), '')
        lyudi[k] = {
            'inn': inn, 'mesto': mesta.get(inn, 9999), 'predpriyatie': nashi.get(inn, ''),
            'chelovek': chel, 'nomer': nomer, 'dolzhnost': dolzh,
            'ssylka': ssyl, 'chem': (r.get('chem_podtverzhdena')
                                     or r.get('chem_dokazana_rol') or '')[:90],
            'citata': re.sub(r'\s+', ' ', (r.get('citata') or r.get('osnovanie') or ''))[:260],
            'fajl': os.path.basename(p), 'fajlov': 1,
        }

for v in sorted(lyudi.values(), key=lambda x: (x['mesto'], x['chelovek'])):
    print('\n--- место %s | %s | ИНН %s' % (v['mesto'], v['predpriyatie'][:40], v['inn']))
    print('    %s — %s' % (v['chelovek'], v['nomer']))
    print('    должность дословно: «%s»' % v['dolzhnost'][:100])
    print('    чем: %s' % v['chem'])
    print('    ссылка: %s' % (v['ssylka'][:100] or '—'))
    print('    основание: %s' % v['citata'])
print('ИТОГ ' + json.dumps({'человек': len(lyudi),
                            'предприятий': len({v['inn'] for v in lyudi.values()})},
                           ensure_ascii=False))
