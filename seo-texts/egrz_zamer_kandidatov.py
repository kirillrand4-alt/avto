# -*- coding: utf-8 -*-
"""Замер кандидатов из металинз по ЖИВОМУ ЕГРЗ. Слово без числа в работу не идёт.

Провайдер даёт идеи. Идея — не факт: «пневмо» тоже звучало разумно, а дало 74 строки про
пневмопробойник. Поэтому каждый кандидат получает три числа из реестра:
  ВСЕГО      сколько записей в реестре содержат подстроку;
  НОВЫХ      сколько из них НЕ попали в нашу выгрузку из 1 419 записей — это и есть
             прибавка, ради которой всё затевалось;
  ПРИМЕРЫ    три живых названия, чтобы человек глазами понял, что именно поймано.
Контроль: выдуманное слово «нипрятозаумень» обязано дать 0.

Порядок вывода — по НОВЫМ, а не по «всего»: слово, которое ловит то же самое, что мы уже
взяли, стоит ноль, как бы велико ни было его «всего».
"""
import collections
import io
import json
import os
import re
import subprocess
import sys
import time

KAT = os.path.dirname(os.path.abspath(__file__))
BAZA = 'https://open-api.egrz.ru/api/PublicRegistrationBook'
UZHE = os.path.join(KAT, 'EGRZ-NASHA-TEMA-2.jsonl')
VYHOD = os.path.join(KAT, 'ZAMER-KANDIDATOV.csv')
KONTROL = 'нипрятозаумень'


def zapros(f, top=3, schet=True):
    args = ['curl', '-sS', '-m', '90', '--get',
            '--data-urlencode', '$filter=' + f,
            '--data-urlencode', '$top=' + str(top)]
    if schet:
        args += ['--data-urlencode', '$count=true']
    args.append(BAZA)
    for att in range(3):
        try:
            r = subprocess.run(args, capture_output=True, timeout=120)
            t = r.stdout.decode('utf-8', 'replace')
            if t.startswith('{'):
                return json.loads(t)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3 + att * 5)
    return None


# --- что у нас уже есть: ключи карточек и их названия
uzhe_klyuchi = set()
for s in io.open(UZHE, encoding='utf-8'):
    if s.strip():
        d = json.loads(s)
        uzhe_klyuchi.add(d.get('ssylka', ''))
print('в нашей выгрузке карточек: %d' % len(uzhe_klyuchi))

# --- собираем кандидатов из всех файлов металинз
kand = {}
for put in sorted(os.listdir(KAT)):
    if not put.startswith('metalinza-') or not put.endswith('.md'):
        continue
    slug = put[len('metalinza-'):-3]
    for line in io.open(os.path.join(KAT, put), encoding='utf-8'):
        if not line.strip().startswith('КАНДИДАТ'):
            continue
        ch = [x.strip() for x in line.split('|')]
        if len(ch) < 3:
            continue
        slovo = ch[1].strip().strip('«»"\'` ').lower()
        # Провайдер иногда оборачивает подстроку в кавычки или дописывает пояснение в
        # скобках — берём только саму подстроку, иначе contains не найдёт ничего и слово
        # получит честный, но ложный ноль.
        slovo = re.sub(r'\s*\(.*?\)\s*', ' ', slovo).strip()
        if not slovo or len(slovo) < 4 or "'" in slovo:
            continue
        if slovo not in kand:
            kand[slovo] = {'pochemu': ch[2][:200], 'shum': (ch[3][:200] if len(ch) > 3 else ''),
                           'linzy': set()}
        kand[slovo]['linzy'].add(slug)
print('кандидатов всего: %d (из них названы двумя и более линзами: %d)'
      % (len(kand), len([k for k, v in kand.items() if len(v['linzy']) > 1])))

d = zapros("contains(tolower(ExpertiseObjectName),'%s')" % KONTROL, top=1)
print('КОНТРОЛЬ «%s»: %s записей%s' % (KONTROL, (d or {}).get('@odata.count'),
                                       '' if (d or {}).get('@odata.count') == 0
                                       else '  ВНИМАНИЕ: контроль пробит'))

stroki = []
for i, (slovo, v) in enumerate(sorted(kand.items()), start=1):
    f = "contains(tolower(ExpertiseObjectName),'%s')" % slovo
    d = zapros(f, top=3)
    if d is None:
        print('%3d/%d  %-34s ОТКАЗ СЕТИ — не измерено' % (i, len(kand), slovo))
        stroki.append({'slovo': slovo, 'vsego': '', 'novyh_v_probe': '',
                       'linz': len(v['linzy']), 'linzy': ' '.join(sorted(v['linzy'])),
                       'pochemu': v['pochemu'], 'shum': v['shum'], 'primery': 'НЕ ИЗМЕРЕНО'})
        continue
    vsego = d.get('@odata.count') or 0
    proba = d.get('value') or []
    nov = len([z for z in proba
               if 'https://egrz.ru/organisation/reestr/detail/' + str(z.get('Key') or '')
               not in uzhe_klyuchi])
    prim = ' // '.join(re.sub(r'\s+', ' ', str(z.get('ExpertiseObjectName') or ''))[:90]
                       for z in proba[:3])
    stroki.append({'slovo': slovo, 'vsego': vsego, 'novyh_v_probe': '%d из %d' % (nov, len(proba)),
                   'linz': len(v['linzy']), 'linzy': ' '.join(sorted(v['linzy'])),
                   'pochemu': v['pochemu'], 'shum': v['shum'], 'primery': prim})
    print('%3d/%d  %-34s всего %6d   новых в пробе %d/%d' % (i, len(kand), slovo, vsego,
                                                             nov, len(proba)))
    time.sleep(0.3)

import csv  # noqa: E402
with io.open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, delimiter=';', fieldnames=['slovo', 'vsego', 'novyh_v_probe',
                                                     'linz', 'linzy', 'pochemu', 'shum',
                                                     'primery'])
    w.writeheader()
    for s in stroki:
        w.writerow(s)

est = [s for s in stroki if isinstance(s['vsego'], int)]
print('\n########## ИТОГ')
print('  измерено кандидатов: %d, не измерено из-за сети: %d'
      % (len(est), len(stroki) - len(est)))
print('  дали 0 записей ..... %d' % len([s for s in est if s['vsego'] == 0]))
print('  дали 1-9 ........... %d' % len([s for s in est if 0 < s['vsego'] < 10]))
print('  дали 10-99 ......... %d' % len([s for s in est if 10 <= s['vsego'] < 100]))
print('  дали 100 и больше .. %d' % len([s for s in est if s['vsego'] >= 100]))
print('  сумма «всего» по всем ненулевым: %d (с пересечениями)'
      % sum(s['vsego'] for s in est))
print('\n  ТОП-30 ПО ЧИСЛУ ЗАПИСЕЙ:')
for s in sorted(est, key=lambda z: -z['vsego'])[:30]:
    print('   %7d  %-32s [линз %d]  %s' % (s['vsego'], s['slovo'], s['linz'],
                                           s['primery'][:78]))
print('\n  файл: %s' % VYHOD)
