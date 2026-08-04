# -*- coding: utf-8 -*-
"""Что успел собрать прогон по компаниям — из ПОТОКА, а не из лога задания.

Задание раннера умирает по таймауту молча: вывод не доезжает, и по нему нельзя
отличить «не стартовал» от «работал и оборвался». Поток отвечает на это сам.
"""
import collections
import json
import os
import time

POTOK = r'C:\sender\_ops\p25-tp-po-kompaniyam.jsonl'
if not os.path.exists(POTOK):
    print('ИТОГ ' + json.dumps({'поток': 'не создан — прогон не стартовал'},
                               ensure_ascii=False))
    raise SystemExit

sch = collections.Counter()
kart_vsego = tenderov = 0
stroki = []
for ln in open(POTOK, encoding='utf-8'):
    try:
        z = json.loads(ln)
    except Exception:  # noqa: BLE001
        sch['строка не разобралась (обрыв записи)'] += 1
        continue
    if z.get('err'):
        sch['предприятие не открылось'] += 1
        continue
    k = z.get('kartochek', 0)
    kart_vsego += k
    tenderov += z.get('tenderov', 0)
    sch['страниц упало'] += z.get('stranic_upalo', 0)
    stroki.append((z.get('mesto', 9999), z.get('tp_name') or z.get('predpriyatie', ''),
                   z.get('tenderov', 0), z.get('novyh', 0), k))

for m, nm, t, n, k in sorted(stroki):
    print('  место %4s  %-42s тендеров %4d, новых %4d, карточек %4d' % (m, nm[:42], t, n, k))
print('ИТОГ ' + json.dumps({
    'предприятий пройдено': len(stroki), 'тендеров найдено': tenderov,
    'КАРТОЧЕК СКАЧАНО': kart_vsego,
    'минут с последней записи': round((time.time() - os.path.getmtime(POTOK)) / 60, 1),
    'прочее': dict(sch)}, ensure_ascii=False))
