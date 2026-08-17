# -*- coding: utf-8 -*-
"""Почему у 712 файлов ИНН не нашёлся — правда нет или мы плохо смотрим."""
import io
import json
import os
import sys

sys.path.insert(0, r'C:\sender\server')
import hozyain_domena as H  # noqa: E402

без = []
for s in io.open(os.path.join(r'C:\sender\server', 'hozyain_domena.jsonl'), encoding='utf-8'):
    try:
        d = json.loads(s)
    except Exception:
        continue
    if d.get('итог') == 'ИНН на страницах нет':
        без.append(d)
примеры = []
for d in без[:8]:
    текст, домен, заголовок = H._разобрать(os.path.join(H.ОТСТОЙНИК, d['файл']))
    низ = текст[-600:]
    примеры.append({'домен': домен, 'знаков': len(текст), 'заголовок': заголовок[:50],
                    'есть_слово_инн': 'ИНН' in текст or 'инн' in текст.lower(),
                    'хвост': низ[-160:]})
print(json.dumps({'без_инн_всего': len(без), 'примеры': примеры},
                 ensure_ascii=False, indent=1)[-2600:])
