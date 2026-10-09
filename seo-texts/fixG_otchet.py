# -*- coding: utf-8 -*-
"""fixG (локально): отчёт об отборе и замене (без номеров телефонов) -> текст для дропа.

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


L = ['ЗАМЕНА 13 ПОМЕЧЕННЫХ КОМПАНИЙ ПАНЕЛИ MEYER (fixG, 09.10.2026)', '',
     'Владелец 09.10: «выкинь их, добавь из последнего списка нормальных компаний».', '',
     'УБРАНЫ (строки каталога – в arhiv_<таблица> того же каталога, назначения – в arhiv_company_assignment базы продаж; '
     'действий продавцов по ним не было):']
for u in sorted(p['ubrat'], key=lambda x: (x['prodavec'], x['inn'])):
    L.append('  %-12s %-44s у %-8s | %s' % (u['inn'], u['predpriyatie'][:44], FIO.get(u['prodavec'], u['prodavec']), u['pometka_ocheredi']))
L += ['', 'ДОБАВЛЕНЫ (метка «База 3», файл 3 «номера без ролей»; место – в рейтинге скрипта отбора Базы 3 среди тех, кого нет в панели):']
for o in p['otobrano']:
    c = komp[o['inn']]
    b = ball[o['inn']]
    L.append('  место %2d · %s · %s · %s (%s) · выручка %.0f млн за %s · ОКВЭД %s (%s)' % (
        o['mesto'], o['inn'], c['predpriyatie'], gorod(c.get('adres')), c['region'], (c['vyruchka_rub'] or 0) / 1e6, c.get('fin_god'),
        c['okved'], c.get('otrasl')))
    L.append('      свой сайт %s: %s' % (o['sayt'], '; '.join(o['dokaz'])))
    L.append('      лучший контакт: %s' % bez_nomera(flagi.get(o['inn'], {}).get('lpr_kratko') or c.get('lpr_kratko')))
    L.append('      продавец: %s · ступень %d · балл очереди %.1f' % (FIO[p['prodavcy'][o['inn']]], STUP[b['stupen']], b['ball_ocheredi']))
L += ['', 'ОТБРАКОВАНЫ по порядку рейтинга, пока не набралось 13 (%d):' % len(p['otkaz'])]
for o in p['otkaz']:
    L.append('  место %2d · %s · %s: %s' % (o['mesto'], o['inn'], o['nazvanie'], ' | '.join(o['prichiny'])))
L += ['', 'ПРОВЕРЕНЫ ПРО ЗАПАС после 13-го (не понадобились; «годна» – прошла все проверки, кроме подписей номеров):']
for o in p['zapas']:
    L.append('  место %2d · %s · %s: %s' % (o['mesto'], o['inn'], o['nazvanie'], 'годна' if o['zapas'] else ' | '.join(o['prichiny'])))
L += ['', 'КАЧЕСТВО ОЧЕРЕДЕЙ (показатели отчёта E2)', '', p['tablica_do'], '', posle.strip(), '',
      'Журнал «было/стало» боевого прогона: fixG-zhurnal-%s.json (удалённые строки целиком, назначения, вставки, холдинг, флаги).'
      % z['vremya'],
      'Архив в каталоге C:\\centro2\\data\\meyer_baza1.db: arhiv_company, arhiv_contact, arhiv_person, arhiv_company_source '
      '(+ пустые по этим ИНН arhiv_holding_chlen, arhiv_fact, arhiv_signal), метка arhiv_data «%s»; в базе продаж – '
      'arhiv_company_assignment.' % z['metka_arhiva'],
      'Копии баз до записи (не для отката целиком): %s' % z['bekap']]
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
