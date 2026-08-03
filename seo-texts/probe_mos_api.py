# -*- coding: utf-8 -*-
"""Жив ли API Портала поставщиков Москвы — проверка С СЕРВЕРА, а не из песочницы.

ПОВОД. Записано, что домен `zakupki.mos.ru` не отвечает «ни с раннера, ни из песочницы»,
и путь `api/Cssp/Purchase/Query`, которым 30 июля за один день сняли 5 681 строку, объявлен
потерянным. Из песочницы он действительно рвёт соединение (Connection reset by peer), но
это диагноз песочницы, а не площадки: с сервера владельца тот же адрес отдал 200.
Здесь проверяется не доступность домена, а то, что ОТВЕТ ПРИГОДЕН — что в теле лежит JSON
с процедурами, а не заглушка «включите JavaScript» с кодом 200.
"""
import json
import urllib.parse
import urllib.request

BAZA = 'https://zakupki.mos.ru/api/Cssp/Purchase/Query'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def zapros(slovo, skip=0, take=3):
    dto = {'filter': {'nameLike': slovo}, 'skip': skip, 'take': take,
           'order': [{'field': 'relevance', 'desc': True}]}
    u = BAZA + '?queryDto=' + urllib.parse.quote(json.dumps(dto, ensure_ascii=False))
    req = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=40) as r:
        telo = r.read().decode('utf-8', 'replace')
    return r.status, telo


for slovo in ('центробежный компрессор', 'воздуходувка'):
    try:
        st, telo = zapros(slovo)
        try:
            d = json.loads(telo)
            items = d.get('items') if isinstance(d, dict) else None
            print(f'{slovo!r}: HTTP {st}, JSON разобран, count={d.get("count") if isinstance(d, dict) else "?"}, '
                  f'items={len(items) if items is not None else "нет ключа items"}')
            if items:
                print('   первая:', json.dumps(items[0], ensure_ascii=False)[:400])
            elif isinstance(d, dict):
                print('   ключи ответа:', list(d)[:12])
        except ValueError:
            print(f'{slovo!r}: HTTP {st}, НО ЭТО НЕ JSON — первые 300 знаков:')
            print('   ', telo[:300].replace('\n', ' '))
    except Exception as e:  # noqa: BLE001
        print(f'{slovo!r}: {type(e).__name__}: {str(e)[:200]}')
