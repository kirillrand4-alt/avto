# -*- coding: utf-8 -*-
"""Куда сервер владельца может ходить, а куда нет. Замер, а не догадка.

ПОВОД. Цепочка справочников подразделений вернула шесть заданий подряд с
`URLError: [Errno 111] Connection refused` и итогом «обработано 0». По правилу В8 ноль —
отказ инструмента, пока не доказано обратное, а «Connection refused» на СЕРВЕРЕ и
«Connection reset» из ПЕСОЧНИЦЫ это разные болезни: первая означает, что соединение
некуда открыть (нет прокси/закрыт порт), вторая — что его рвёт удалённая сторона.
Отличить можно только замером с самого сервера.
"""
import json
import urllib.request

CELI = [
    ('xmlriver.com', 'https://xmlriver.com/'),
    ('google', 'https://www.google.com/'),
    ('zakupki.mos.ru', 'https://zakupki.mos.ru/'),
    ('mos API', 'https://zakupki.mos.ru/api/Cssp/Purchase/Query?queryDto=%7B%22take%22:1%7D'),
    ('tender.pro', 'https://tender.pro/'),
    ('roseltorg', 'https://www.roseltorg.ru/'),
    ('gost ЭПБ', 'https://mpb.gosnadzor.ru/'),
    ('evraz', 'https://www.evraz.com/ru/'),
]
out = {}
for imya, u in CELI:
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(u, headers={'User-Agent': 'curl/8.5.0'}), timeout=25)
        out[imya] = f'{r.status} ({len(r.read(2000))} байт прочитано)'
    except Exception as e:  # noqa: BLE001
        out[imya] = f'{type(e).__name__}: {str(e)[:120]}'
print(json.dumps(out, ensure_ascii=False, indent=1))
