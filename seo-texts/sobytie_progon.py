# -*- coding: utf-8 -*-
"""Испытание обоих приборов на выборке старых строк signals.

Владелец: «нам нужно не текущие которые собранные, а новые собрать». Поэтому старые строки
здесь - ИСПЫТАТЕЛЬНЫЙ МАТЕРИАЛ, а не цель: 60 штук, дальше приборы едут на новый поток.

Что делает:
  1. контроль разборщика дат заведомо негодным входом (сам разборщик, без сети);
  2. нормализация даты по выборке: сколько строк получили дату, откуда, кто остался без
     даты и ПОЧЕМУ (причина словами у каждой строки);
  3. классификация стадии пачками, в каждую пачку подмешана ВЫДУМАННАЯ строка;
  4. отдельный заведомо ломаный вызов провайдера - доказать, что сбой не голосует;
  5. печать 15 строк «текст рядом со стадией» глазами владельца;
  6. запись результата в jsonl (оттуда он уезжает в enrich.db отдельным шагом).

Запуск: python3 sobytie_progon.py --vyborka <file.json> [--karty <file.json>] --out <file.jsonl>
`--karty` - даты карточек ВК и seen_news, добытые на сервере (rid -> {vk_epoch, seen_ts}).
"""
import argparse
import collections
import json
import os
import re
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)

import sobytie_data as SD          # noqa: E402
import sobytie_stadiya as SS       # noqa: E402

p = argparse.ArgumentParser()
p.add_argument('--vyborka', required=True)
p.add_argument('--karty', default='')
p.add_argument('--out', required=True)
p.add_argument('--razmer-pachki', type=int, default=12)
p.add_argument('--bez-provaydera', action='store_true')
a = p.parse_args()

rows = json.load(open(a.vyborka, encoding='utf-8'))
karty = json.load(open(a.karty, encoding='utf-8')) if a.karty and os.path.exists(a.karty) else {}
print('строк в выборке: %d, карточек с сервера: %d' % (len(rows), len(karty)))

# ---------------------------------------------------------------- 1. контроль дат
print('\n=== КОНТРОЛЬ 1: разборщик даты на заведомо негодном входе ===')
prokoly = SD.kontrol()
print('проколов: %d' % len(prokoly))
for x in prokoly:
    print('  ! ' + x)

# ---------------------------------------------------------------- 2. даты
print('\n=== ДАТЫ по выборке ===')
for r in rows:
    k = karty.get(str(r['rid'])) or {}
    r['data'] = SD.normalizovat(ts=r.get('ts'), source_url=r.get('source_url'),
                                what=r.get('what'), source=r.get('source'),
                                vk_epoch=k.get('vk_epoch'), vzyatie=r.get('updated_at'),
                                seen_ts=k.get('seen_ts'))
otkuda = collections.Counter(r['data']['data_otkuda'] or 'НЕТ ДАТЫ' for r in rows)
print('откуда взята дата:')
for k, v in otkuda.most_common():
    print('  %-12s %d' % (k, v))
bez = [r for r in rows if not r['data']['data_iso']]
print('без даты: %d' % len(bez))
for k, v in collections.Counter(r['data']['prichina_bez_daty'][:60] for r in bez).most_common():
    print('  причина: %-62s %d' % (k, v))
print('дата плана (срок из текста) есть у %d строк'
      % sum(1 for r in rows if r['data']['data_plana']))
print('дата взятия известна у %d строк' % sum(1 for r in rows if r['data']['data_vzyatiya']))

# ---------------------------------------------------------------- 3-4. стадия
if a.bez_provaydera:
    print('\n(провайдер отключён ключом --bez-provaydera)')
    sys.exit(0)

print('\n=== КОНТРОЛЬ 2: заведомо ломаный вызов провайдера ===')
slom = SS.stadiya_pachkoy([{'id': rows[0]['rid'], 'tekst': rows[0]['what']}],
                          model='model-kotoroy-net-999', attempts=1)
sl = slom.get(rows[0]['rid'], {})
print('  статус: %s, стадия: %r, ошибка: %s'
      % (sl.get('status'), sl.get('stadiya'), (sl.get('oshibka') or '')[:110]))
print('  сбой отделён от «не знаю»: %s'
      % ('ДА' if sl.get('status') == 'sboy_provaydera' and not sl.get('stadiya') else 'НЕТ'))

print('\n=== КЛАССИФИКАЦИЯ СТАДИИ (в каждой пачке одна выдуманная строка) ===')
itog = {}
primanki_itog = {}
pachki = [rows[i:i + a.razmer_pachki] for i in range(0, len(rows), a.razmer_pachki)]
for n, pach in enumerate(pachki):
    zapisi = [{'id': r['rid'], 'tekst': r['what']} for r in pach]
    nabor, pids = SS.podmeshat_primanki(zapisi, skolko=1, smeshchenie=n)
    otvet = SS.stadiya_pachkoy(nabor)
    for pid in pids:
        primanki_itog[pid] = otvet.get(pid, {'status': 'net_v_otvete'})
    for r in pach:
        itog[r['rid']] = otvet.get(r['rid'], {'status': 'net_v_otvete', 'stadiya': ''})
    st = collections.Counter(v.get('status') for k, v in otvet.items() if k not in pids)
    print('  пачка %d: строк %d, %s' % (n + 1, len(pach), dict(st)))

print('\n=== КОНТРОЛЬ 3: что получили выдуманные тексты ===')
plohih = 0
for pid, v in primanki_itog.items():
    uver = v.get('uverennost')
    plohо = bool(v.get('stadiya')) and uver == 'высокая'
    plohih += 1 if plohо else 0
    print('  %-14s статус=%-14s стадия=%-14s уверенность=%-8s выдумка=%s %s'
          % (pid, v.get('status'), v.get('stadiya') or '-', uver or '-',
             v.get('vydumka'), 'ПРОКОЛ' if plohо else ''))
print('  приманок с уверенной стадией: %d из %d' % (plohih, len(primanki_itog)))

# ---------------------------------------------------------------- итоги и запись
for r in rows:
    r['stadiya'] = itog.get(r['rid'], {})

st = collections.Counter(r['stadiya'].get('status') for r in rows)
print('\n=== СТАТУСЫ ОТВЕТА ===')
for k, v in st.most_common():
    print('  %-16s %d' % (k, v))
golosovali = [r for r in rows if r['stadiya'].get('status') == 'ok']
print('\n=== РАСПРЕДЕЛЕНИЕ ПО СТАДИЯМ (голосуют только %d строк со статусом ok) ===' % len(golosovali))
raspr = collections.Counter(r['stadiya'].get('stadiya') for r in golosovali)
for s in SS.STADII:
    print('  %-16s %d' % (s, raspr.get(s, 0)))
rannie = sum(raspr.get(s, 0) for s in SS.RANNIE)
print('  три самые ранние (%s): %d из %d классифицированных'
      % (', '.join(SS.RANNIE), rannie, len(golosovali)))
otr = collections.Counter(r['stadiya'].get('otrasl') for r in golosovali)
print('  отрасли: %s' % dict(otr.most_common()))

print('\n=== 15 СТРОК ГЛАЗАМИ: текст рядом со стадией ===')
pokaz = [r for r in rows if r['stadiya'].get('status') == 'ok'][:15]
if len(pokaz) < 15:
    pokaz += [r for r in rows if r not in pokaz][:15 - len(pokaz)]
for r in pokaz:
    s = r['stadiya']
    print('\n[%s] стадия=%s (%s) отрасль=%s дата=%s/%s'
          % (r['rid'], s.get('stadiya') or 'НЕ ОПРЕДЕЛЕНА', s.get('uverennost') or '-',
             s.get('otrasl') or '-', r['data']['data_iso'] or 'нет',
             r['data']['data_otkuda'] or r['data']['prichina_bez_daty'][:22]))
    print('   текст: %s' % re.sub(r'\s+', ' ', (r['what'] or ''))[:300])
    if s.get('zacepka'):
        print('   зацепка: %s' % s['zacepka'][:110])

with open(a.out, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps({'rid': r['rid'], 'inn': r.get('inn'), 'source': r.get('source'),
                            'source_url': r.get('source_url'), 'what': r.get('what'),
                            'event_type': r.get('event_type'), 'hotness': r.get('hotness'),
                            **r['data'], **{('st_' + k): v for k, v in r['stadiya'].items()}},
                           ensure_ascii=False) + '\n')
print('\nзаписано: %s (%d строк)' % (a.out, len(rows)))

print('\n=========== ИТОГ ПРОГОНА ===========')
print('дата есть у %d из %d; без даты %d' % (len(rows) - len(bez), len(rows), len(bez)))
print('статусы стадии: %s' % dict(st))
print('три ранние стадии: %d строк' % rannie)
print('приманок с уверенной стадией: %d из %d (норма 0)' % (plohih, len(primanki_itog)))
