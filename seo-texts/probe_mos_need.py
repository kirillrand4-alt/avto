# -*- coding: utf-8 -*-
"""Последняя проверка по Москве: `Need/Query` отдал 405, значит ручка есть и хочет POST.

ПОЧЕМУ ИМЕННО ОНА. Ссылки в собранном 30 июля файле выглядят как `zakupki.mos.ru/need/5438800`,
и тип строки — «закупка по потребностям». То есть 5 681 строка пришла из раздела потребностей.
`Purchase/Query` на GET работает, но его полнотекстовый фильтр валится в 500; `Need/Query`
на GET даёт 405 — не 404. Разница решает: 404 это «нет такой ручки», 405 это «ручка есть,
метод не тот». Проверяю POST.
"""
import json
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def post(baza, put, dto, tajm=60):
    u = f'https://{baza}{put}'
    telo = json.dumps(dto, ensure_ascii=False).encode()
    req = urllib.request.Request(u, data=telo, method='POST', headers={
        'User-Agent': UA, 'Accept': 'application/json', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=tajm) as r:
            t = r.read().decode('utf-8', 'replace')
        if t.lstrip()[:1] not in '{[':
            return 'не JSON', t[:120]
        return json.loads(t), ''
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}', e.read().decode('utf-8', 'replace')[:160]
    except Exception as e:  # noqa: BLE001
        return f'{type(e).__name__}', str(e)[:120]


FORMY = [
    ('пустой (контроль)', {'skip': 0, 'take': 3}),
    ('nameLike', {'filter': {'nameLike': 'компрессор'}, 'skip': 0, 'take': 3}),
    ('name', {'filter': {'name': 'компрессор'}, 'skip': 0, 'take': 3}),
    ('inn заказчика', {'filter': {'customerInn': '7707083893'}, 'skip': 0, 'take': 3}),
]
for baza in ('old.zakupki.mos.ru', 'zakupki.mos.ru'):
    for imya, dto in FORMY:
        d, hvost = post(baza, '/api/Cssp/Need/Query', dto)
        if isinstance(d, dict):
            items = d.get('items') or []
            print(f'{baza:<20} {imya:<18} count={d.get("count")} items={len(items)}')
            for it in items[:2]:
                print('     ·', (it.get('name') or '')[:110])
        else:
            print(f'{baza:<20} {imya:<18} {d}  {hvost!r}')
