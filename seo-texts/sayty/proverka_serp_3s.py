# -*- coding: utf-8 -*-
"""Проверка 240 найденных URL двумя признаками — в песочнице, параллельно и бесплатно.

Сервер отдал только адреса из выдачи. Признак свой: ИНН на странице (сильный, как в исходном
инструменте) ИЛИ редкое слово названия + город из ЕГРЮЛ (замерен: 0 ложных из 33 контрольных).
Уровень доверия пишется в каждую строку — склеивать их нельзя.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, '/home/user/work')
from proverka_kandidatov import ЧАСТЫЕ, слова, текст_сайта  # noqa: E402

журнал = json.load(open('SERP-only-3s.json', encoding='utf-8'))
карта = json.load(open('inn_karta_3s.json', encoding='utf-8'))
цели = [r for r in журнал if r.get('сайт')]
print(f'адресов на проверку: {len(цели)}', flush=True)


def проверить(r):
    инн = r['инн']
    c = карта.get(инн) or {}
    имя = c.get('name') or r.get('имя') or ''
    город = re.sub(r'^(г|город|пгт|с|пос)\s*\.?\s*', '', (c.get('gorod') or '').lower()).strip()
    город = re.sub(r'\s*(р-н|район|городской округ|го)\b.*$', '', город).strip()
    t = текст_сайта(r['сайт'])
    if not t:
        return {'inn': инн, 'sayt': r['сайт'], 'uroven': 'страницы не скачались'}
    цифры = re.sub(r'\D', '', инн)
    if re.search(r'(?<!\d)' + цифры + r'(?!\d)', re.sub(r'[\s\-]', '', t)):
        return {'inn': инн, 'sayt': r['сайт'], 'uroven': 'ИНН на странице'}
    сл = слова(имя)
    нашлось = [w for w in сл if w[:7] in t]
    есть_город = bool(город) and len(город) >= 4 and город[:6] in t
    if нашлось and есть_город:
        # Сигналы обязаны быть независимы: если слово названия и есть город целиком,
        # проверку пройдёт городской портал.
        if not (нашлось[0] == город or (len(нашлось[0]) <= len(город) + 1
                                        and нашлось[0].startswith(город))):
            return {'inn': инн, 'sayt': r['сайт'], 'uroven': 'имя+город',
                    'pochemu': f'«{нашлось[0]}» + «{город}»'}
    return {'inn': инн, 'sayt': r['сайт'], 'uroven': 'не подтверждён'}


with ThreadPoolExecutor(max_workers=12) as пул:
    рез = list(пул.map(проверить, цели))
import collections
c = collections.Counter(x['uroven'] for x in рез)
print('\n'.join(f'  {v:>4}  {k}' for k, v in c.most_common()))
годные = [x for x in рез if x['uroven'] in ('ИНН на странице', 'имя+город')]
print(f'\nПОДТВЕРЖДЕНО ВСЕГО: {len(годные)} из {len(цели)}')
json.dump(годные, open('sayty-podtverzhdennye-3s.json', 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(рез, open('sayty-vse-proverki-3s.json', 'w', encoding='utf-8'), ensure_ascii=False)
