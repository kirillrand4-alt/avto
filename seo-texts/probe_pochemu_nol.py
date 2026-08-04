# -*- coding: utf-8 -*-
"""Ноль телефонов на 150 запросах — отказ прибора или честный ноль. Смотрю сами записи.

В песочнице тот же модуль на том же классе целей давал телефон примерно у каждого шестого.
На сервере — ноль из 150. Такая разница не бывает от данных, значит либо запросы не уходят,
либо уходят не те, либо выдача пустая. Печатаю: сколько записей со сбоем, сколько с пустой
выдачей, сколько документов приходило, и три запроса целиком.
"""
import collections
import json

put = r'C:\seostat\drop\3s-obratnyy-server.jsonl'
sch = collections.Counter()
primery = []
for ln in open(put, encoding='utf-8'):
    if not ln.strip():
        continue
    z = json.loads(ln)
    sch['всего'] += 1
    if z.get('err'):
        sch[f"сбой: {str(z['err'])[:60]}"] += 1
    sch[f"документов в выдаче: {min(len(z.get('naydeno') or []), 5)}"] += 1
    if len(primery) < 3:
        primery.append({k: v for k, v in z.items() if k in
                        ('inn', 'fio', 'predpriyatie', 'zapros', 'err')} |
                       {'найдено_док': len(z.get('naydeno') or []),
                        'контактов': len(z.get('kontakty') or [])})
print(json.dumps({'счёт': dict(sch), 'примеры': primery}, ensure_ascii=False, indent=1))
