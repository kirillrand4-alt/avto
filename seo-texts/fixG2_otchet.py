# -*- coding: utf-8 -*-
"""fixG2 (локально): отчёт – Воронеж убран, замены, краснодарские у Ерохина и Беляева, перестановки (без номеров).

    python3 fixG_otchet.py <plan.json> <журнал боевого прогона.json> <таблица «после» (txt)> <выход.txt>
"""
import json
import re
import sys

PLAN, ZH, POSLE, OUT = sys.argv[1:5]
p = json.load(open(PLAN, encoding='utf-8'))
z = json.load(open(ZH, encoding='utf-8'))
posle = open(POSLE, encoding='utf-8').read()
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


L = ['ВОРОНЕЖ ИЗ БАЗЫ, ЗАМЕНЫ ИЗ ФАЙЛА 3, КРАСНОДАРСКИЕ – ЕРОХИНУ И БЕЛЯЕВУ (fixG2, 09.10.2026)', '',
     'Владелец 09.10: «краснодарских отдай Ерохину и Беляеву; воронежских убери из базы, заменив неплохими снова; '
     'по итогу так же по 150 у всех, приоритеты примерно равны».', '',
     'ИТОГ: годных замен в файле 3 нашлось %d из %d – рейтинг скрипта отбора Базы 3 исчерпан (последнее место %d), '
     'требования не ослаблялись; поэтому у каждого продавца по %s, а не по 150.' % (
         len(p['otobrano']), p['nuzhno'], max([o['mesto'] for o in p['otobrano'] + p['otkaz']]), sorted(set(p['cel'].values()))), '',
     'УБРАНЫ ВОРОНЕЖСКИЕ (%d; строки каталога – в arhiv_<таблица>, назначения – в arhiv_company_assignment; '
     'действий продавцов не было; в группах холдингов ни одна не состояла):' % len(p['ubrat'])]
for u in sorted(p['ubrat'], key=lambda x: (x['prodavec'], x['inn'])):
    L.append('  %-12s %-44s у %-8s | %s' % (u['inn'], u['predpriyatie'][:44], FIO.get(u['prodavec'], u['prodavec']), u.get('bazy') or ''))
L += ['', 'ДОБАВЛЕНЫ (метка «База 3», файл 3; место – в рейтинге скрипта отбора Базы 3; продолжение с места 50):']
for o in p['otobrano']:
    c = komp[o['inn']]
    b = ball[o['inn']]
    L.append('  место %2d · %s · %s · %s (%s) · выручка %.0f млн за %s · ОКВЭД %s (%s)' % (
        o['mesto'], o['inn'], c['predpriyatie'], gorod(c.get('adres')), c['region'], (c['vyruchka_rub'] or 0) / 1e6, c.get('fin_god'),
        c['okved'], c.get('otrasl')))
    L.append('      свой сайт %s: %s' % (o['sayt'], '; '.join(o['dokaz'])))
    L.append('      лучший контакт: %s' % bez_nomera(flagi.get(o['inn'], {}).get('lpr_kratko') or c.get('lpr_kratko')))
    L.append('      продавец: %s · ступень %d · балл очереди %.1f' % (FIO[p['prodavcy'][o['inn']]], STUP[b['stupen']], b['ball_ocheredi']))
for x in p.get('ne_vzyaty_nomera', []):
    L.append('  не взят номер у %s: %s' % (x['inn'], x['pochemu']))
L += ['', 'ОТБРАКОВАНЫ (места 50–76, %d):' % len(p['otkaz'])]
for o in p['otkaz']:
    L.append('  место %2d · %s · %s: %s' % (o['mesto'], o['inn'], o['nazvanie'], ' | '.join(o['prichiny'])))
import collections
pot = collections.Counter((m['ot'], m['komu']) for m in p['peremeshcheniya'])
L += ['', 'ПЕРЕЕХАЛИ (%d; минимум перемещений при ровном качестве – MILP; действий продавцов ни у одной не было): %s' % (
    len(p['peremeshcheniya']), ', '.join('%s → %s %d' % (FIO[a], FIO[b], n) for (a, b), n in sorted(pot.items())))]
for m in sorted(p['peremeshcheniya'], key=lambda m: (m['region'] != 'Краснодарский край', m['ot'], m['inn'])):
    L.append('  %-12s %-40s %-24s %s → %s · ступень %d · %s' % (m['inn'], m['nazvanie'][:40], m['region'][:24], FIO[m['ot']],
                                                             FIO[m['komu']], m['stupen'], m['prichina'][:110]))
L += ['', 'КРАСНОДАРСКИЕ: было %s; стало %s' % (
    ', '.join('%s %d' % (FIO[k], v) for k, v in sorted(p['krasnodar']['do'].items())),
    ', '.join('%s %d' % (FIO[k], v) for k, v in sorted(p['krasnodar']['posle'].items())))]
L += ['', 'КАЧЕСТВО ОЧЕРЕДЕЙ (показатели отчёта E2)', '', p['tablica_do'], '', posle.strip(), '',
      'Журнал «было/стало» боевого прогона: fixG2-zhurnal-%s.json (удалённые строки целиком, назначения, перестановки, вставки, флаги).'
      % z['vremya'],
      'Архив в каталоге C:\\centro2\\data\\meyer_baza1.db: arhiv_company, arhiv_contact, arhiv_person, arhiv_company_source '
      '(+ пустые по этим ИНН arhiv_holding_chlen, arhiv_fact, arhiv_signal), метка arhiv_data «%s»; в базе продаж – '
      'arhiv_company_assignment.' % z['metka_arhiva'],
      'Копии баз до записи (не для отката целиком): %s' % z['bekap']]
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
