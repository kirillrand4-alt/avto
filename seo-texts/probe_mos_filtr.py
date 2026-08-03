# -*- coding: utf-8 -*-
"""Каким полем фильтруется выдача: счётчик 5 052 781 одинаков у всех моих вариантов.

ПОВОД. Канал восстановлен: `old.zakupki.mos.ru/api/Cssp/Purchase/Query?queryDto=...` отдаёт
JSON на GET. Но фильтр не применяется — и «nameLike», и «name», и вовсе пустой запрос дают
один и тот же count = 5 052 781, то есть весь портал. Взять всё и фильтровать у себя нельзя:
пять миллионов строк по 3 записи за запрос — это не сбор, а отказ. Значит имя поля другое.
Здесь перебираются написания, а признак успеха один: счётчик ИЗМЕНИЛСЯ по сравнению с
пустым запросом. Совпал — фильтр молча проигнорирован, и это надо видеть, а не считать
удачей.
"""
import json
import urllib.parse
import urllib.request

BAZA = 'https://old.zakupki.mos.ru/api/Cssp/Purchase/Query'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
SLOVO = 'центробежный компрессор'


def sprosit(dto, tajm=60):
    u = BAZA + '?queryDto=' + urllib.parse.quote(json.dumps(dto, ensure_ascii=False))
    req = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=tajm) as r:
            d = json.loads(r.read().decode('utf-8', 'replace'))
        return d.get('count'), (d.get('items') or [])
    except Exception as e:  # noqa: BLE001
        return f'{type(e).__name__}: {str(e)[:70]}', []


BAZOVYY, _ = sprosit({'skip': 0, 'take': 3})
print(f'пустой запрос: count={BAZOVYY}  (это «весь портал», эталон для сравнения)\n')

VARIANTY = [
    ('текст в filter.nameLike', {'filter': {'nameLike': SLOVO}, 'skip': 0, 'take': 3}),
    ('текст в filter.name', {'filter': {'name': SLOVO}, 'skip': 0, 'take': 3}),
    ('текст в filter.text', {'filter': {'text': SLOVO}, 'skip': 0, 'take': 3}),
    ('текст в filter.query', {'filter': {'query': SLOVO}, 'skip': 0, 'take': 3}),
    ('текст в filter.searchString', {'filter': {'searchString': SLOVO}, 'skip': 0, 'take': 3}),
    ('текст в filter.namePart', {'filter': {'namePart': SLOVO}, 'skip': 0, 'take': 3}),
    ('текст в textQuery', {'textQuery': SLOVO, 'skip': 0, 'take': 3}),
    ('текст в searchText', {'searchText': SLOVO, 'skip': 0, 'take': 3}),
    ('текст в query', {'query': SLOVO, 'skip': 0, 'take': 3}),
    ('текст в text', {'text': SLOVO, 'skip': 0, 'take': 3}),
    ('текст в name', {'name': SLOVO, 'skip': 0, 'take': 3}),
    ('текст в keyword', {'keyword': SLOVO, 'skip': 0, 'take': 3}),
    ('filter.namePartial', {'filter': {'namePartial': SLOVO}, 'skip': 0, 'take': 3}),
    ('одно слово: компрессор', {'filter': {'nameLike': 'компрессор'}, 'skip': 0, 'take': 3}),
]
for imya, dto in VARIANTY:
    c, items = sprosit(dto)
    if isinstance(c, str):
        print(f'  {imya:<30} ОШИБКА {c}')
        continue
    znak = 'ФИЛЬТР РАБОТАЕТ' if c != BAZOVYY else 'проигнорирован (счётчик тот же)'
    print(f'  {imya:<30} count={c:<10} {znak}')
    if c != BAZOVYY and items:
        print('       первая:', (items[0].get('name') or '')[:120])
