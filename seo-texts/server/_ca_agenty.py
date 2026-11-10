# -*- coding: utf-8 -*-
"""Что дают агенты набора ca: счётчики по ca-glubokiy.jsonl (без ФИО и номеров)."""
import collections, json, os
п = r'C:\sender\server\ca-glubokiy.jsonl'
с = collections.Counter(); ключи = collections.Counter()
if os.path.exists(п):
    for s in open(п, encoding='utf-8', errors='replace'):
        try:
            з = json.loads(s)
        except ValueError:
            continue
        с['записей'] += 1
        ключи.update(k for k, v in з.items() if v)
        с['итог=' + str(з.get('итог'))[:20]] += 1
        if з.get('сайт'):
            с['нашёл сайт'] += 1
        люди = з.get('люди') or з.get('контакты') or з.get('номера') or []
        if люди:
            с['есть люди/контакты'] += 1
            с['людей всего'] += len(люди)
            if any((x.get('лпр') == 'да') if isinstance(x, dict) else False for x in люди):
                с['есть ЛПР'] += 1
print('===ИТОГ===', dict(с)); print('ключи', dict(ключи.most_common(25)))
