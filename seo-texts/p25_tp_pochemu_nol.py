# -*- coding: utf-8 -*-
"""Отчего у 42 из 45 предприятий ноль: имя не нашлось или cid не совпал. Различить.

42 нуля подряд — снова повод проверить прибор, а не записать ответ. Причин ровно две,
и они лечатся по-разному:

    выдача ПУСТА (na_pervoy_stranice = 0)     -> имя не нашлось на площадке;
                                                 лечится другим написанием имени
    выдача ЕСТЬ, но своих ноль                -> наш cid не совпал ни с одной строкой;
                                                 лечится сверкой по ИНН, а не по cid

Поля для этого различения я записала в поток заранее, потому и различаю теперь без
единого нового запроса к площадке.
"""
import collections
import json
import os

POTOK = r'C:\sender\_ops\p25-tp-po-kompaniyam.jsonl'
sch = collections.Counter()
primery = collections.defaultdict(list)

for ln in open(POTOK, encoding='utf-8'):
    try:
        z = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    if z.get('err'):
        sch['ошибка запроса'] += 1
        continue
    vsego = z.get('na_pervoy_stranice', 0)
    svoih = z.get('tenderov', 0)
    chuzhih = z.get('chuzhih_otseyano', 0)
    imya = z.get('imya_poiska', '')
    if svoih:
        sch['СВОИ НАЙДЕНЫ'] += 1
        continue
    if not vsego:
        sch['имя на площадке не нашлось (выдача пуста)'] += 1
        primery['имя не нашлось'].append((imya, z.get('cid'), z.get('predpriyatie', '')[:40]))
    else:
        sch['выдача есть, но НИ ОДНОЙ строки с нашим cid'] += 1
        primery['cid не совпал'].append((imya, z.get('cid'), vsego, chuzhih))

for k, v in primery.items():
    print('--- %s (%d) ---' % (k, len(v)))
    for x in v[:12]:
        print('   ', x)
for k, v in sch.most_common():
    print('REC %s\t%d' % (k, v))
print('ИТОГ ' + json.dumps({'записей в потоке': sum(sch.values())}, ensure_ascii=False))
