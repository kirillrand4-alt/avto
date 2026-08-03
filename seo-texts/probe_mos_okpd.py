# -*- coding: utf-8 -*-
"""Обход сломанного полнотекстового поиска: фильтр по ОКПД, а не по словам.

ПОВОД. `filter.nameLike` на `old.zakupki.mos.ru` валится в 500 при ЛЮБОЙ обёртке — с
`order`, без него, с пустыми списками, со строковой сортировкой. Неизвестные поля портал
молча игнорирует, а это отвечает 500, то есть поле своё и ломается уже внутри — похоже,
лежит полнотекстовый индекс, а не наш запрос кривой.

ПОЧЕМУ ОКПД ЛУЧШЕ СЛОВ, а не просто «вместо». Слово «компрессор» ловит и холодильник, и
автокондиционер, и ремонт; ОКПД 28.13.2 это «насосы воздушные или вакуумные; компрессоры
воздушные или газовые» — классификатор самой закупки, то есть свидетельство площадки, а не
наша догадка по названию. Если работает, это ещё и полнее: попадут закупки, где слова
«компрессор» в названии нет вовсе.
"""
import json
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')
PUSTO = 5052781
OKPD = ['28.13.2', '28.13.21', '28.13.22', '28.13.23', '28.13.24', '28.13.25', '28.13.26',
        '28.13.28']


def sprosit(baza, put, dto, tajm=60):
    u = f'https://{baza}{put}?queryDto=' + urllib.parse.quote(json.dumps(dto, ensure_ascii=False))
    req = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=tajm) as r:
            telo = r.read().decode('utf-8', 'replace')
        if telo.lstrip()[:1] not in '{[':
            return 'оболочка SPA', []
        d = json.loads(telo)
        return d.get('count'), (d.get('items') or [])
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}', []
    except Exception as e:  # noqa: BLE001
        return f'{type(e).__name__}', []


P = '/api/Cssp/Purchase/Query'
PROBY = [
    ('okpdCodes списком', {'filter': {'okpdCodes': OKPD}, 'take': 3, 'skip': 0}),
    ('okpd списком', {'filter': {'okpd': OKPD}, 'take': 3, 'skip': 0}),
    ('okpdIds списком', {'filter': {'okpdIds': OKPD}, 'take': 3, 'skip': 0}),
    ('okpdCode одной строкой', {'filter': {'okpdCode': '28.13.2'}, 'take': 3, 'skip': 0}),
    ('okpdCodes + order', {'filter': {'okpdCodes': OKPD},
                           'order': [{'field': 'relevance', 'desc': True}],
                           'withCount': True, 'take': 3, 'skip': 0}),
]
print('=== фильтр по ОКПД на old.zakupki.mos.ru ===')
for imya, dto in PROBY:
    c, items = sprosit('old.zakupki.mos.ru', P, dto)
    if isinstance(c, str):
        print(f'  {imya:<26} ОШИБКА {c}')
        continue
    print(f'  {imya:<26} count={c:<10} ' + ('ФИЛЬТР РАБОТАЕТ' if c != PUSTO else 'проигнорирован'))
    if c != PUSTO:
        for it in items[:3]:
            print('       ·', (it.get('name') or '')[:110])

print('\n=== другие ручки поиска, вдруг полнотекст живёт там ===')
for put in ('/api/Cssp/Purchase/PostQuery', '/api/Cssp/Purchase/LightQuery',
            '/api/Cssp/Purchase/QueryAutocomplete', '/api/Cssp/PurchaseSearch/Query',
            '/api/Contract/Query', '/api/Cssp/Need/Query'):
    c, items = sprosit('old.zakupki.mos.ru', put, {'filter': {'nameLike': 'компрессор'},
                                                   'take': 3, 'skip': 0})
    print(f'  {put:<40} {c}')
