# -*- coding: utf-8 -*-
r"""Расход токенов этой сессии: по дням и по моделям.

Считаем по расшифровке Claude Code — в ней у каждого ответа лежит usage:
вход, чтение и запись кэша, выход. «Всего» — сумма всех четырёх: именно
столько прошло через модель.
"""
import json
import os
from collections import defaultdict

ПУТЬ = '/root/.claude/projects/-home-user-avto'
по_дням = defaultdict(lambda: {'ответов': 0, 'вход': 0, 'кэш_чтение': 0,
                               'кэш_запись': 0, 'выход': 0})
по_моделям = defaultdict(lambda: {'ответов': 0, 'выход': 0, 'всего': 0})
файлов = 0
for имя in sorted(os.listdir(ПУТЬ)):
    if not имя.endswith('.jsonl'):
        continue
    файлов += 1
    with open(os.path.join(ПУТЬ, имя), encoding='utf-8', errors='replace') as f:
        for строка in f:
            if '"usage"' not in строка:
                continue
            try:
                з = json.loads(строка)
            except Exception:  # noqa: BLE001
                continue
            м = з.get('message') or {}
            u = м.get('usage') or {}
            if not u:
                continue
            день = str(з.get('timestamp') or '')[:10]
            вх = int(u.get('input_tokens') or 0)
            кч = int(u.get('cache_read_input_tokens') or 0)
            кз = int(u.get('cache_creation_input_tokens') or 0)
            вых = int(u.get('output_tokens') or 0)
            д = по_дням[день]
            д['ответов'] += 1
            д['вход'] += вх
            д['кэш_чтение'] += кч
            д['кэш_запись'] += кз
            д['выход'] += вых
            мод = по_моделям[str(м.get('model') or '?')]
            мод['ответов'] += 1
            мод['выход'] += вых
            мод['всего'] += вх + кч + кз + вых

строки = []
итого = {'ответов': 0, 'всего': 0, 'выход': 0}
for день in sorted(по_дням):
    д = по_дням[день]
    всего = д['вход'] + д['кэш_чтение'] + д['кэш_запись'] + д['выход']
    итого['ответов'] += д['ответов']
    итого['всего'] += всего
    итого['выход'] += д['выход']
    строки.append('%s  ответов %5d   всего %13s   выход %9s   кэш-чтение %13s'
                  % (день[8:10] + '.' + день[5:7], д['ответов'],
                     '{:,}'.format(всего).replace(',', ' '),
                     '{:,}'.format(д['выход']).replace(',', ' '),
                     '{:,}'.format(д['кэш_чтение']).replace(',', ' ')))
строки.append('%s  ответов %5d   всего %13s   выход %9s'
              % ('ИТОГО', итого['ответов'],
                 '{:,}'.format(итого['всего']).replace(',', ' '),
                 '{:,}'.format(итого['выход']).replace(',', ' ')))
строки.append('')
строки.append('по моделям:')
for м, з in sorted(по_моделям.items(), key=lambda x: -x[1]['всего']):
    строки.append('  %-26s ответов %5d  выход %9s  всего %13s'
                  % (м[:26], з['ответов'],
                     '{:,}'.format(з['выход']).replace(',', ' '),
                     '{:,}'.format(з['всего']).replace(',', ' ')))
строки.append('')
строки.append('файлов расшифровки: %d' % файлов)
print('\n'.join(строки))
