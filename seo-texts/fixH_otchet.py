# -*- coding: utf-8 -*-
"""fixH (локально): отчёт – кого убрали (активная сделка Meyer, доказательство), кого добавили (источник), сколько не
хватило, качество очередей до/после, Битрикс до -> после (без номеров телефонов).

    python3 fixH_otchet.py <plan.json> <журнал боевого прогона.json> <таблица «после» (txt)> <выход.txt> [kandidaty.json]
"""
import collections
import json
import re
import sys

PLAN, ZH, POSLE, OUT = sys.argv[1:5]
p = json.load(open(PLAN, encoding='utf-8'))
z = json.load(open(ZH, encoding='utf-8'))
posle = open(POSLE, encoding='utf-8').read()
kand = json.load(open(sys.argv[5], encoding='utf-8')) if len(sys.argv) > 5 else []
FIO = {'meyer1': 'Пяткова', 'meyer2': 'Ерохин', 'meyer3': 'Беляев', 'meyer4': 'Волков'}
STUP = {4: 800, 3: 600, 2: 400, 1: 200, 0: 0}
flagi = {f['inn']: f['stalo'] for f in z['flagi']}
ball = {x['inn']: x for x in z['naznacheniya_novye'] if 'stupen' in x and 'ball_ocheredi' in x}
komp = {c['inn']: c for c in p['kompanii']}


def bez_nomera(s):
    s = re.sub(r'\s*·?\s*\+7[\d\s()\-]{9,}\d(\s*доб\.\s*\d+)?', '', s or '')
    return re.sub(r':\s*(\(|$)', r' \1', s).strip(' ·:')


def gorod(adres):
    m = re.search(r'\b(?:г\.|город|пгт\.?|с\.|п\.|пос\.|рп\.?|д\.)\s*([А-ЯЁ][а-яёА-ЯЁ-]+(?:\s[А-ЯЁ][а-яё-]+)?)', adres or '')
    return m.group(1) if m else (adres or '').split(',')[1].strip() if ',' in (adres or '') else ''


ubr = p['ubrat']
sch_u = collections.Counter(FIO[u['prodavec']] for u in ubr)
sch_n = collections.Counter(FIO[v] for v in p['prodavcy'].values())
bx = p['bitrix_itog']
L = ['ВЫГРУЗКА СДЕЛОК БИТРИКСА 09.10: УБРАНЫ КОМПАНИИ С АКТИВНОЙ СДЕЛКОЙ MEYER, ДОБОР ДО 150, ПОЛЯ БИТРИКСА (fixH, 09.10.2026)', '',
     'Владелец 09.10: «если есть активные сейчас в базе (сделка Meyer в работе) – выкинь их», добрать до 150 у каждого тем же '
     'порядком источников (остаток файла 6 -> остаток файла 2 -> файл 3 с правилом «название + город»).', '',
     'ИТОГ: убрано %d (%s), добрано %d – все из остатка файла 6 (%s); не хватило: 0. По 150 у каждого, краснодарские – '
     'Ерохин %d / Беляев %d. В рабочем каталоге 0 компаний с активной сделкой Meyer.' % (
         len(ubr), ', '.join('%s %d' % (k, v) for k, v in sorted(sch_u.items())), len(p['prodavcy']),
         ', '.join('%s %d' % (k, v) for k, v in sorted(sch_n.items())), p['krasnodar']['posle'].get('meyer2', 0),
         p['krasnodar']['posle'].get('meyer3', 0)), '',
     'УБРАНЫ – активная сделка Meyer (АКТИВНА = да в meyer_all.csv); действий продавцов ни по одной не было; строки – в arhiv_*:']
for u in ubr:
    L.append('  %s · %s · %s · была у %s · %s' % (u['inn'], u['predpriyatie'], u['region'], FIO[u['prodavec']], u['bazy']))
    for d in u['dokaz']:
        L.append('      %s' % d)
L += ['', 'ДОБАВЛЕНЫ (метка «База 6», источник – остаток файла 6, места после 14; файлы 2 и 3 не понадобились):']
for o in p['otobrano']:
    c = komp[o['inn']]
    b = ball[o['inn']]
    L.append('  место %3d · %s · %s · %s (%s) · выручка %.0f млн за %s · ОКВЭД %s (%s)' % (
        o['mesto'], o['inn'], c['predpriyatie'], gorod(c.get('adres')), c['region'], (c['vyruchka_rub'] or 0) / 1e6, c.get('fin_god'),
        c['okved'], c.get('otrasl')))
    L.append('      свой сайт %s: %s' % (o['sayt'], '; '.join(x for x in o['dokaz'] if x.startswith(('ИНН', 'ОГРН', 'руковод', 'юрадрес')))))
    L.append('      лучший контакт: %s' % bez_nomera(flagi.get(o['inn'], {}).get('lpr_kratko') or c.get('lpr_kratko')))
    L.append('      Битрикс: %s' % (p['bitrix'][o['inn']]['bitrix_kc_info'] or 'сделок нет'))
    L.append('      продавец: %s · ступень %d · балл очереди %.1f' % (FIO[p['prodavcy'][o['inn']]], STUP[b['stupen']], b['ball_ocheredi']))
for x in p.get('ne_vzyaty_nomera', []):
    L.append('  не взят номер у %s: %s' % (x['inn'], x['pochemu']))
pri = collections.Counter()
for o in p['otkaz']:
    for pr in o['prichiny']:
        pri[re.sub(r'\(.*', '', pr.split(':')[0]).strip()[:70]] += 1
L += ['', 'ОТБРАКОВАНЫ В ОСТАТКЕ ФАЙЛА 6 (места 15–%d): %d; причины: %s' % (
    max(x['mesto'] for x in p['otobrano'] + p['otkaz']), len(p['otkaz']), '; '.join('%s – %d' % kv for kv in pri.most_common()))]
for o in p['otkaz']:
    L.append('  место %3d · %s · %s: %s' % (o['mesto'], o['inn'], o['nazvanie'], ' | '.join(o['prichiny'])[:300]))
pot = collections.Counter((m['ot'], m['komu']) for m in p['peremeshcheniya'])
L += ['', 'ПЕРЕЕХАЛИ (%d; для ровного качества очередей, MILP; действий продавцов ни у одной не было): %s' % (
    len(p['peremeshcheniya']), ', '.join('%s → %s %d' % (FIO[a], FIO[b], n) for (a, b), n in sorted(pot.items())))]
for m in p['peremeshcheniya']:
    L.append('  %-12s %-40s %-24s %s → %s · ступень %d' % (m['inn'], m['nazvanie'][:40], m['region'][:24], FIO[m['ot']],
                                                       FIO[m['komu']], m['stupen']))
L += ['', 'БИТРИКС (компаний; «до» – прежний справочник КЦ на тех 600, что были; «после» – выгрузка 09.10 на итоговые 600):',
      '  галочка Битрикса (bitrix_kc): %d -> %d' % (bx['do']['галочка Битрикса'], bx['po']['галочка Битрикса']),
      '  клиенты Meyer: поля не было -> %d' % bx['po']['клиенты Meyer'],
      '  клиенты СЦ: %d -> %d' % (bx['do']['клиенты СЦ'], bx['po']['клиенты СЦ']),
      '  с активными сделками КЦ/СЦ: поля не было -> %d' % bx['po']['с активными сделками КЦ/СЦ'],
      '  по продавцам после: ' + '; '.join('%s %s' % (k, ', '.join('%s %d' % kv for kv in v.items())) for k, v in bx['po_prodavcam'].items())]
L += ['', 'КАЧЕСТВО ОЧЕРЕДЕЙ (показатели отчёта E2)', '', p['tablica_do'], '', posle.strip(), '',
      'Журнал «было/стало» боевого прогона: fixH-zhurnal-%s.json (убранные строки, назначения, перестановки, вставки, '
      'поля Битрикса «было/стало» по каждой компании, флаги).' % z['vremya'],
      'Архив в каталоге C:\\centro2\\data\\meyer_baza1.db: arhiv_company, arhiv_contact, arhiv_person, arhiv_company_source, '
      'arhiv_holding_chlen (+ arhiv_fact, arhiv_signal), метка arhiv_data «%s»; в базе продаж – arhiv_company_assignment.'
      % z['metka_arhiva'],
      'Копии баз до записи (не для отката целиком): %s' % z['bekap']]
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
