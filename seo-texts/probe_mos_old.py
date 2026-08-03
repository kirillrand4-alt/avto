# -*- coding: utf-8 -*-
"""Проверка догадки: API портала живёт на old.zakupki.mos.ru и отвечает на GET.

ПОВОД, И ЭТО СПОР С СОСЕДНЕЙ СЕССИЕЙ, А НЕ СОГЛАСИЕ. Соседи записали, что метод `Query`
принимает POST с JSON-телом. Замер с сервера владельца говорит обратное: POST на
`zakupki.mos.ru/api/Cssp/Purchase/Query` отдаёт от nginx `405 Not Allowed`, а тот же POST на
`old.zakupki.mos.ru` — честный JSON `{"message":"The requested resource does not support
http method 'POST'"}`. Второе важнее первого: раз ответ пришёл ОТ ПРИЛОЖЕНИЯ, а не от
оболочки SPA, значит API стоит именно там, и метод у него GET.
"""
import json
import urllib.parse
import urllib.request

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')


def get(u, tajm=60):
    req = urllib.request.Request(u, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=tajm) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


# Форма запроса — та, которой снимали 30 июля. Пробую несколько написаний фильтра: за три
# дня мог смениться не только хост, но и имя поля.
DTO = [
    {'filter': {'nameLike': 'центробежный компрессор'}, 'skip': 0, 'take': 3},
    {'nameLike': 'центробежный компрессор', 'skip': 0, 'take': 3},
    {'filter': {'name': 'центробежный компрессор'}, 'skip': 0, 'take': 3},
    {'skip': 0, 'take': 3},
]
for baza in ('https://old.zakupki.mos.ru', 'https://zakupki.mos.ru'):
    for i, dto in enumerate(DTO, 1):
        u = baza + '/api/Cssp/Purchase/Query?queryDto=' + urllib.parse.quote(
            json.dumps(dto, ensure_ascii=False))
        st, t = get(u)
        vid = 'JSON' if t.lstrip()[:1] in '{[' else (
            'оболочка SPA' if '<!doctype' in t[:60].lower() else 'иное')
        hvost = ''
        if vid == 'JSON':
            try:
                d = json.loads(t)
                if isinstance(d, dict):
                    items = d.get('items') or d.get('Items')
                    hvost = f' count={d.get("count", d.get("Count", "?"))} items={len(items) if items is not None else "нет"}'
                    if items:
                        hvost += '\n      первая: ' + json.dumps(items[0], ensure_ascii=False)[:300]
            except ValueError:
                pass
        print(f'{baza[8:26]:<22} dto#{i} {st} {vid:<14} {t[:110].replace(chr(10), " ")!r}{hvost}')
