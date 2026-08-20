# -*- coding: utf-8 -*-
r"""Проба переразбора БЕЗ вызовов провайдера: склейка и порядок очереди.

Проверяем ровно то, что чинили:
  1. склейка не теряет непустое старое поле, когда новый ответ скупой;
  2. в отбор действительно попадают устаревшие паспорта;
  3. компании БЕЗ паспорта идут первыми, переразбор — в хвосте.
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r'C:\sender\server')
import site_facts as SF  # noqa: E402

d = {}

# 1. Склейка.
старый = json.dumps({'продукция': ['мука в/с', 'отруби'],
                     'оборудование_линии': ['мельничный комплекс'],
                     'энергохозяйство': ['компрессорная'],
                     'мощности': ['120 т/сут'], 'уверенность': 'высокая'},
                    ensure_ascii=False)
новый = {'продукция': [], 'оборудование_линии': ['новая линия фасовки'],
         'энергохозяйство': [], 'новости': [{'дата': '2026-08', 'заголовок': 'цех'}],
         'уверенность': 'низкая'}
с = SF._sliyanie(старый, новый)
d['склейка'] = {
    'продукция_сохранилась': с.get('продукция') == ['мука в/с', 'отруби'],
    'новое_поле_победило': с.get('оборудование_линии') == ['новая линия фасовки'],
    'энергохозяйство_сохранилось': с.get('энергохозяйство') == ['компрессорная'],
    'новости_добавились': bool(с.get('новости')),
    'признак_КЦ': (с.get('разбор_КЦ') or {}).get('признак_КЦ'),
}

# 2-3. Отбор ровно как в цикле.
c = sqlite3.connect('file:C:/sender/enrich.db?mode=ro', uri=True, timeout=60)
готовые = {str(x[0]) for x in c.execute(
    "select inn from site_facts where coalesce(popytok,0) >= 3 "
    "or coalesce(otlozheno_do,0) > ? "
    "or (coalesce(facts_json,'')<>'' and coalesce(format,0) >= ?)",
    (time.time(), SF.FORMAT))}
свежесть = {str(x[0]): SF._vremya_pasporta(x[1]) for x in c.execute(
    "select inn, coalesce(ts,'') from site_facts where coalesce(facts_json,'')<>''")}
c.close()
сырьё = SF._iz_kesha(200, готовые, свежесть)
komp = [k for k in сырьё if k.get('pererazbor') or k['inn'] not in готовые][:200]
метки = [bool(k.get('pererazbor')) for k in сырьё]
d['отбор'] = {
    'вернул': len(сырьё),
    'на_переразбор': sum(метки),
    'без_паспорта': len(метки) - sum(метки),
    'дошло_до_разбора': len(komp),
    'переразбор_строго_в_хвосте': метки == sorted(метки),
    'предел_переразборов': SF.PREDEL_PERERAZBOROV,
}
print(json.dumps(d, ensure_ascii=False, indent=1))
