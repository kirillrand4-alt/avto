# -*- coding: utf-8 -*-
"""КОНТРОЛЬ склейки: смотреть глазами, а не верить числу.

ЭТО ПЕРВЫЙ, ПАКЕТНЫЙ ПРОТОТИП. Рабочий сборщик — `p3_proekt_ingest.py`: он принимает
ПОТОК по одному событию и пишет в `enrich.db`. Прототип оставлен только для сверки
чисел: у него нет заслона «объекты разные», поэтому проектов он даёт меньше, а самый
большой получается смесью (18 улик против 12). Числа отчёта берутся НЕ отсюда.

Печатает:
  1. как разошлись по проектам ИНН с наибольшим числом сигналов (заслон против слипания);
  2. десяток случайных склеек — тексты рядом, чтобы владелец судил сам;
  3. самый большой проект целиком;
  4. КОНТРОЛЬ С ЗАВЕДОМО НЕГОДНЫМ ВХОДОМ: подставные сигналы, которые склеиваться
     НЕ ДОЛЖНЫ, и подставной текст без мест — ноль доказывается так же, как находка.

Запуск: python3 p3_proekt_kontrol.py --lokalno <signals.json> [--skleek 10]
"""
import collections
import io
import json
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p3_proekt_lib as L        # noqa: E402
import p3_proekty_sborka as S    # noqa: E402

A = sys.argv[1:]
SIG, PROEKTY, DF, POG = S.main(A)
po_inn = collections.defaultdict(list)
for p in PROEKTY:
    po_inn[p['inn_zakazchik']].append(p)
sig_po_inn = collections.Counter(s['inn'] for s in SIG)

print('=' * 78)
print('1. ИНН С НАИБОЛЬШИМ ЧИСЛОМ СИГНАЛОВ: во сколько проектов разошлись')
print('=' * 78)
for inn, n in sig_po_inn.most_common(10):
    pr = po_inn[inn]
    print('ИНН %s: сигналов %d -> проектов %d ; размеры %s'
          % (inn, n, len(pr), sorted((x['dokazatelstv'] for x in pr), reverse=True)))
    for x in sorted(pr, key=lambda z: -z['dokazatelstv'])[:14]:
        print('    [%2d улик] место=%-22s объект=%-26s работы=%s'
              % (x['dokazatelstv'], (x['mesto'] or x['region'] or '—')[:22],
                 (x['obekt'] or '—')[:26], (x['tip_rabot'] or '—')[:34]))
    print()

print('=' * 78)
print('2. СЛУЧАЙНЫЕ СКЛЕЙКИ: тексты рядом')
print('=' * 78)
skleeny = [p for p in PROEKTY if p['dokazatelstv'] >= 2]
random.seed(7)
n_pok = int(A[A.index('--skleek') + 1]) if '--skleek' in A else 10
for p in random.sample(skleeny, min(n_pok, len(skleeny))):
    print('-' * 78)
    print('ПРОЕКТ %s  ИНН %s  улик %d  источников %d'
          % (p['proekt_id'], p['inn_zakazchik'], p['dokazatelstv'], p['istochnikov']))
    print('  ключ: %s' % p['klyuch_sostav'])
    print('  почему слиплись: %s' % (p['sklejka_prichiny'] or '—')[:300])
    for u in p['dokazatelstva'][:6]:
        print('  · %-22s %-16s %s' % (u['istochnik'][:22], u['event_type'][:16],
                                      (u['data'] or '')[:10]))
        print('      %s' % u['citata'].replace('\n', ' ')[:300])
print()

print('=' * 78)
print('3. САМЫЙ БОЛЬШОЙ ПРОЕКТ ЦЕЛИКОМ')
print('=' * 78)
b = max(PROEKTY, key=lambda p: p['dokazatelstv'])
print('ПРОЕКТ %s ИНН %s улик %d источников %d ключ: %s'
      % (b['proekt_id'], b['inn_zakazchik'], b['dokazatelstv'], b['istochnikov'],
         b['klyuch_sostav']))
for u in b['dokazatelstva']:
    print('  · %-22s %s' % (u['istochnik'][:22], u['citata'].replace('\n', ' ')[:220]))
print()

print('=' * 78)
print('4. КОНТРОЛЬ С ЗАВЕДОМО НЕГОДНЫМ ВХОДОМ')
print('=' * 78)
proby = [
    ('одно предприятие, разные города',
     [{'_rid': -1, 'inn': '0000000001', 'source': 'a.ru', 'what':
       'Модернизация газоочистки на заводе в Братске Иркутской области',
       'event_type': 'модернизация', 'source_url': 'http://a', 'sum': '', 'hotness': '3',
       'ts': '', 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''},
      {'_rid': -2, 'inn': '0000000001', 'source': 'b.ru', 'what':
       'Модернизация газоочистки на заводе в Волгограде Волгоградской области',
       'event_type': 'модернизация', 'source_url': 'http://b', 'sum': '', 'hotness': '3',
       'ts': '', 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''}], 2),
    ('одно предприятие, одно место, один объект — должны слипнуться',
     [{'_rid': -3, 'inn': '0000000002', 'source': 'a.ru', 'what':
       'В Тайшете строится Тайшетский алюминиевый завод, ведётся монтаж газоочистки',
       'event_type': 'новый завод', 'source_url': 'http://a', 'sum': '', 'hotness': '3',
       'ts': '', 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''},
      {'_rid': -4, 'inn': '0000000002', 'source': 'b.ru', 'what':
       'Тайшетский алюминиевый завод в Тайшете: пусконаладка систем газоочистки',
       'event_type': 'запуск линии', 'source_url': 'http://b', 'sum': '', 'hotness': '3',
       'ts': '', 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''}], 1),
    ('разрыв дат больше окна — склейки быть не должно',
     [{'_rid': -5, 'inn': '0000000003', 'source': 'a.ru', 'what':
       'В Тайшете строится Тайшетский алюминиевый завод, монтаж газоочистки',
       'event_type': 'новый завод', 'source_url': 'http://a', 'sum': '', 'hotness': '3',
       'ts': '2019-01-10', 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''},
      {'_rid': -6, 'inn': '0000000003', 'source': 'b.ru', 'what':
       'В Тайшете Тайшетский алюминиевый завод: монтаж газоочистки продолжается',
       'event_type': 'новый завод', 'source_url': 'http://b', 'sum': '', 'hotness': '3',
       'ts': '2026-01-10', 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''}], 2),
    ('пустые тексты — не должны слипаться в один проект-помойку',
     [{'_rid': -7 - i, 'inn': '0000000004', 'source': 's%d.ru' % i, 'what': '',
       'event_type': '', 'source_url': 'http://s', 'sum': '', 'hotness': '',
       'ts': '', 'updated_at': '2026-01-01', 'suspect': '0', 'inn_conf': ''}
      for i in range(5)], 5),
]
for imya, syr, zhdem in proby:
    s = [L.razobrat_signal(r) for r in syr]
    df, zg, st = S.statistika(s)
    for x in s:
        x['yak'] = S.yakorya(x, df, zg, st)
        x['df'] = df
        x['zontik'] = (len(x['goroda']) + len(x['regiony'])) >= L.ZONTIK_MEST
    got = S.sobrat_proekty(s)
    znak = 'ВЕРНО' if len(got) == zhdem else 'НЕВЕРНО'
    print('  %-58s ждём %d, вышло %d  %s' % (imya[:58], zhdem, len(got), znak))

mus = ('Компрессор винтовой ВК-15 подаёт воздух 2,5 куб. м в минуту при давлении 8 бар; '
       'обслуживание раз в 4000 часов, замена фильтров и масла по регламенту.')
pr = L.razobrat_signal({'_rid': -99, 'inn': '0', 'what': mus, 'event_type': '',
                        'source': '', 'source_url': '', 'sum': '', 'hotness': '',
                        'ts': '', 'updated_at': '', 'suspect': '', 'inn_conf': ''})
print('  текст без места: городов %d, регионов %d  %s'
      % (len(pr['goroda']), len(pr['regiony']),
         'ВЕРНО' if not pr['goroda'] and not pr['regiony'] else
         'НЕВЕРНО: ' + str(pr['goroda'] | pr['regiony'])))
pr2 = L.razobrat_signal({'_rid': -98, 'inn': '0', 'what':
                         'Строительство нового завода в городе Тайшет, Иркутская область',
                         'event_type': '', 'source': '', 'source_url': '', 'sum': '',
                         'hotness': '', 'ts': '', 'updated_at': '', 'suspect': '',
                         'inn_conf': ''})
print('  текст с местом: %s / %s  %s' % (sorted(pr2['goroda']), sorted(pr2['regiony']),
                                         'ВЕРНО' if pr2['goroda'] else 'НЕВЕРНО'))

print()
print('########## ЧИСЛА КОНТРОЛЯ')
print('  проектов                      %5d' % len(PROEKTY))
print('  ИНН с 1 проектом              %5d' % sum(1 for i in po_inn if len(po_inn[i]) == 1))
print('  ИНН, где проектов < сигналов  %5d'
      % sum(1 for i in po_inn if len(po_inn[i]) < sig_po_inn[i]))
print('  погашенных якорей (имя фирмы) %5d' % len(POG))
