# -*- coding: utf-8 -*-
"""Сколько компаний набора ca имеют последнюю запись обхода хуже одной из прежних (только чтение, счётчики)."""
import collections, json
def балл(з):
    стр = з.get('страницы') or []
    ок = sum(1 for _, ст in стр if ст == 'ok')
    ном = [x for x in з.get('номера') or [] if x.get('чей') != 'другая']
    return (1 if з.get('сайт') else 0, ок, len(ном))
посл, лучш = {}, {}
for s in open(r'C:\sender\server\ca-kontakty.jsonl', encoding='utf-8', errors='replace'):
    try: з = json.loads(s)
    except ValueError: continue
    if з.get('итог') != 'ok': continue
    i = з['inn']; посл[i] = з
    if i not in лучш or балл(з) > балл(лучш[i]): лучш[i] = з
с = collections.Counter()
for i, з in посл.items():
    if балл(лучш[i]) > балл(з):
        с['последняя хуже'] += 1
        if лучш[i].get('сайт') and not з.get('сайт'): с['потерян сайт'] += 1
        elif any(ст == 'ok' for _, ст in лучш[i].get('страницы') or []) and not any(ст == 'ok' for _, ст in з.get('страницы') or []): с['сайт не открылся теперь'] += 1
        else: с['меньше контактов'] += 1
print('===ИТОГ===', len(посл), dict(с))
