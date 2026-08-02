# -*- coding: utf-8 -*-
"""Почему dadata дала 1393 руководителя и 8 почт: ответ такой или разбор такой.

Юрзначимый адрес в ЕГРЮЛ обязателен, значит доля 8/1393 — это почти наверняка
не свойство реестра, а мой разбор либо тариф ответа. Смотрим сырой журнал:
какие ключи вообще приходят и в скольких ответах непусто.
"""
import json
import os
from collections import Counter

ЖУРНАЛ = r'C:\sender\server\dadata_celi.jsonl'

ключи = Counter()
непусто = Counter()
всего = 0
образец = None
for ln in open(ЖУРНАЛ, encoding='utf-8', errors='replace'):
    try:
        d = json.loads(ln)
    except Exception:  # noqa: BLE001
        continue
    всего += 1
    for k, v in d.items():
        ключи[k] += 1
        if v not in (None, '', [], {}):
            непусто[k] += 1
    if образец is None and d.get('mgmt_name'):
        образец = {k: (v if not isinstance(v, str) else v[:60])
                   for k, v in d.items()}

print(json.dumps({
    'записей': всего,
    'ключи_встречаются': ключи.most_common(),
    'ключи_непустые': непусто.most_common(),
    'образец': образец,
}, ensure_ascii=False))
