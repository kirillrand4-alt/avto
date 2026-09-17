# -*- coding: utf-8 -*-
"""Портфель проектировщика и застройщика: главная идея веера металинз, проверенная числом.

Четыре линзы из шести независимо сказали одно и то же: перестать искать слово в названии
и пойти от ЛИЦА. Проектировщик, сделавший одну компрессорную, делал их десяток; у
застройщика, который строит компрессорную, в реестре есть и другие объекты.

ГЛАВНАЯ ТЕХНИЧЕСКАЯ НАХОДКА, без которой идея осталась бы разговором. Поля с
организациями — это КОЛЛЕКЦИИ, и обычный contains по ним отдаёт отказ:
    contains(PlannerOrganizations,'7014006319')              -> ОТКАЗ
    PlannerOrganizations/any(o: contains(o,'7014006319'))    -> 66 записей
Первый вариант выглядит как «в реестре ничего нет», второй — работает. Проверено на
ООО «СИБТЕРМ»: у нас по нему было 34 объекта, в реестре их 66.

Здесь считаются ТОЛЬКО числа: сколько заключений у каждого лица всего. Выгрузка самих
записей — следующим шагом, когда владелец посмотрит на цену вопроса.
Контроль: выдуманный ИНН 9999999999 обязан дать 0.
"""
import csv
import io
import json
import os
import subprocess
import time

KAT = os.path.dirname(os.path.abspath(__file__))
BAZA = 'https://open-api.egrz.ru/api/PublicRegistrationBook'
VHOD = os.path.join(KAT, 'EGRZ-NASHA-TEMA-2.jsonl')
VYHOD = os.path.join(KAT, 'PORTFEL-LIC.csv')
KONTROL = '9999999999'


def schet(pole, inn):
    f = "%s/any(o: contains(o,'%s'))" % (pole, inn)
    args = ['curl', '-sS', '-m', '70', '--get', '--data-urlencode', '$filter=' + f,
            '--data-urlencode', '$top=1', '--data-urlencode', '$count=true', BAZA]
    for att in range(3):
        try:
            r = subprocess.run(args, capture_output=True, timeout=100)
            t = r.stdout.decode('utf-8', 'replace')
            if t.startswith('{'):
                return json.loads(t).get('@odata.count')
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 + att * 4)
    return None


stroki = [json.loads(s) for s in io.open(VHOD, encoding='utf-8') if s.strip()]
nasha = [s for s in stroki if s['klass'] == 'НАША ТЕМА']

# сколько объектов ЭТОГО лица уже есть у нас — чтобы прибавка считалась честно
u_nas_p, u_nas_z, imena = {}, {}, {}
for s in stroki:
    for pole, kuda in (('proektirovshchik_inn', u_nas_p), ('zastroyshchik_inn', u_nas_z)):
        i = s.get(pole)
        if i:
            kuda[i] = kuda.get(i, 0) + 1
            imena.setdefault(i, s[pole.replace('_inn', '')][:60])

LICA = []
for s in nasha:
    if s.get('proektirovshchik_inn'):
        LICA.append(('PlannerOrganizations', s['proektirovshchik_inn'], 'проектировщик'))
    if s.get('zastroyshchik_inn'):
        LICA.append(('DeveloperOrganizations', s['zastroyshchik_inn'], 'застройщик'))
LICA = sorted(set(LICA))
print('лиц из «нашей темы» к замеру: %d (проектировщиков %d, застройщиков %d)'
      % (len(LICA), len([x for x in LICA if x[2] == 'проектировщик']),
         len([x for x in LICA if x[2] == 'застройщик'])))

k1 = schet('PlannerOrganizations', KONTROL)
k2 = schet('DeveloperOrganizations', KONTROL)
print('КОНТРОЛЬ ИНН %s: проектировщиком %s, застройщиком %s (ждём 0 и 0)'
      % (KONTROL, k1, k2))

out = []
for n, (pole, inn, rol) in enumerate(LICA, start=1):
    v = schet(pole, inn)
    est = (u_nas_p if rol == 'проектировщик' else u_nas_z).get(inn, 0)
    out.append({'rol': rol, 'inn': inn, 'imya': imena.get(inn, ''),
                'vsego_v_reestre': '' if v is None else v,
                'uzhe_u_nas': est,
                'pribavka': '' if v is None else max(0, v - est)})
    if n % 25 == 0 or n == len(LICA):
        print('  %3d/%d ...' % (n, len(LICA)))
    time.sleep(0.25)

with io.open(VYHOD, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, delimiter=';', fieldnames=['rol', 'inn', 'imya', 'vsego_v_reestre',
                                                     'uzhe_u_nas', 'pribavka'])
    w.writeheader()
    for s in out:
        w.writerow(s)

est = [s for s in out if s['vsego_v_reestre'] != '']
print('\n########## ИТОГ')
print('  измерено лиц: %d, отказов сети: %d' % (len(est), len(out) - len(est)))
for rol in ('проектировщик', 'застройщик'):
    g = [s for s in est if s['rol'] == rol]
    print('  %s: лиц %d · заключений в реестре %d · у нас было %d · ПРИБАВКА %d'
          % (rol, len(g), sum(s['vsego_v_reestre'] for s in g),
             sum(s['uzhe_u_nas'] for s in g), sum(s['pribavka'] for s in g)))
print('  лиц с одним-единственным заключением (случайные): %d'
      % len([s for s in est if s['vsego_v_reestre'] <= 1]))
print('  лиц с 10 и более заключениями (специалисты): %d'
      % len([s for s in est if s['vsego_v_reestre'] >= 10]))
print('\n  ТОП-25 ПО ПРИБАВКЕ:')
for s in sorted(est, key=lambda z: -z['pribavka'])[:25]:
    print('   +%-5d %-13s %s  %s' % (s['pribavka'], s['rol'], s['inn'], s['imya'][:52]))
print('\n  файл: %s' % VYHOD)
