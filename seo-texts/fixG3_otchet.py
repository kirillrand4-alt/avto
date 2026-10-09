# -*- coding: utf-8 -*-
"""fixG3 (локально): отчёт о доборе 8 до 150 (источник каждой, отбраковка по источникам, перестановки; без номеров).

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
kand = json.load(open(sys.argv[5], encoding='utf-8')) if len(sys.argv) > 5 else []
naz_k = {c['inn']: c['nazvanie'] for c in kand}


def bez_nomera(s):
    s = re.sub(r'\s*·?\s*\+7[\d\s()\-]{9,}\d(\s*доб\.\s*\d+)?', '', s or '')
    return re.sub(r':\s*(\(|$)', r' \1', s).strip(' ·:')


def gorod(adres):
    m = re.search(r'\b(?:г\.|город|пгт\.?|с\.|п\.|пос\.|рп\.?|д\.)\s*([А-ЯЁ][а-яёА-ЯЁ-]+(?:\s[А-ЯЁ][а-яё-]+)?)', adres or '')
    return m.group(1) if m else (adres or '').split(',')[1].strip() if ',' in (adres or '') else ''


lpr = p.get('lpr_ne_lichnyy', {})
L = ['ДОБОР 8 КОМПАНИЙ ДО 150 У КАЖДОГО (fixG3, 09.10.2026)', '',
     'Владелец 09.10: «добрать недостающие 8 (по 2 каждому) – остаток файла 6, потом остаток файла 2, потом файл 3 '
     'с ослабленным правилом сайта, переходя к следующему, только если в предыдущем годные кончились».', '',
     'ИТОГ: все 8 – из остатка файла 6 (годных в нём больше, чем нужно), файлы 2 и 3 не понадобились. Кандидатов в остатке '
     'файла 6 после первичного отбора %d (не в панели и не убраны, не Воронеж, основной ОКВЭД даёт сегмент, выручка от 100 млн '
     'без верхнего предела, есть номер со своего сайта). ЛПР с личным номером: в файле таких нет; на страницах своих сайтов '
     'подпись ЛПР у номера нашлась у 14, после проверки глазами личного номера ЛПР не подтвердилось ни у одной (ниже), '
     'поэтому порядок – по баллу файла 6 (скрипт Базы 6: выручка, попадание, лучший контакт).' % len(kand), '',
     'ЛПР СО СТРАНИЦ, НЕ ПОДТВЕРЖДЁННЫЕ КАК ЛИЧНЫЙ НОМЕР:']
for inn, pr in lpr.items():
    L.append('  %s %s: %s' % (inn, naz_k.get(inn, ''), pr))
L.append('  (ещё 6 с подписанным ЛПР не прошли проверку сайта: Брусянские продукты, Молоко Дона и Милково – сайт MLK Group, '
         'Молоко Бурятии, Альянс, Вегус)')
L += ['', 'ДОБАВЛЕНЫ (метка «База 6», источник – остаток файла 6; место – в порядке отбора остатка файла 6):']
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
L += ['', 'ОТБРАКОВАНЫ В ФАЙЛЕ 6 до набора 8 (места 1–14, %d); файлы 2 и 3 – не проверялись (не понадобились):' % len(p['otkaz'])]
for o in p['otkaz']:
    L.append('  место %2d · %s · %s: %s' % (o['mesto'], o['inn'], o['nazvanie'], ' | '.join(o['prichiny'])))
import collections
pot = collections.Counter((m['ot'], m['komu']) for m in p['peremeshcheniya'])
L += ['', 'ПЕРЕЕХАЛИ (%d; новых – по 2 каждому, перестановки – для ровного качества очередей, MILP; действий продавцов ни у одной не было): %s' % (
    len(p['peremeshcheniya']), ', '.join('%s → %s %d' % (FIO[a], FIO[b], n) for (a, b), n in sorted(pot.items())))]
for m in sorted(p['peremeshcheniya'], key=lambda m: (m['region'] != 'Краснодарский край', m['ot'], m['inn'])):
    L.append('  %-12s %-40s %-24s %s → %s · ступень %d · %s' % (m['inn'], m['nazvanie'][:40], m['region'][:24], FIO[m['ot']],
                                                             FIO[m['komu']], m['stupen'], m['prichina'][:110]))
L += ['', 'КРАСНОДАРСКИЕ: было %s; стало %s' % (
    ', '.join('%s %d' % (FIO[k], v) for k, v in sorted(p['krasnodar']['do'].items())),
    ', '.join('%s %d' % (FIO[k], v) for k, v in sorted(p['krasnodar']['posle'].items())))]
L += ['', 'КАЧЕСТВО ОЧЕРЕДЕЙ (показатели отчёта E2)', '', p['tablica_do'], '', posle.strip(), '',
      'Журнал «было/стало» боевого прогона: fixG3-zhurnal-%s.json (назначения, перестановки, вставки, флаги).'
      % z['vremya'],
      'Архив в каталоге C:\\centro2\\data\\meyer_baza1.db: arhiv_company, arhiv_contact, arhiv_person, arhiv_company_source '
      '(+ пустые по этим ИНН arhiv_holding_chlen, arhiv_fact, arhiv_signal), метка arhiv_data «%s»; в базе продаж – '
      'arhiv_company_assignment.' % z['metka_arhiva'],
      'Копии баз до записи (не для отката целиком): %s' % z['bekap']]
open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))
