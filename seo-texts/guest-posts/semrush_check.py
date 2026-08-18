#!/usr/bin/env python3
"""Органика доноров через Semrush групбай-аккаунта владельца.

Зачем: Ahrefs UR показывает вес СТРАНИЦЫ, но не отличает «страница ценная» от
«на сайт закуплено 12 тысяч ссылок». Владелец открыл вручную три дешёвые площадки
из моего списка - у всех трёх органика 0-62 при тысячах бэклинков, то есть
ссылочные фермы, которые мой аудит пропустил. Органический трафик и число ключей
такое не прощают.

Эндпоинт снят с живого запроса панели: POST /dpa/rpc, метод organic.Summary.
Обязателен dateType (без него «Invalid params»). Ответ - массив по 28 базам стран,
нам нужна ru; заодно считаем суммарную органику по всем базам.

    python3 semrush_check.py eyes-15.txt
"""
import json, os, sys, time
import httpx

SP = os.environ.get('SR_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1/scratchpad/sr_cookie.txt')
URL = 'https://sr.groupbuyseo.org/dpa/rpc'
API = '4daff3d2f58fe6b7bde7b8cb33bcf394'
UID = 30530406
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36')


def summary(c, cookie, dom):
    body = {'id': 1, 'jsonrpc': '2.0', 'method': 'organic.Summary',
            'params': {'request_id': 'x1', 'report': 'domain.overview',
                       'userId': UID, 'apiKey': API,
                       'args': {'database': 'ru', 'searchItem': dom,
                                'searchType': 'domain', 'dateType': 'monthly'}}}
    r = c.post(URL, content=json.dumps(body), headers={
        'cookie': cookie, 'content-type': 'application/json; charset=utf-8',
        'user-agent': UA, 'origin': 'https://sr.groupbuyseo.org',
        'referer': f'https://sr.groupbuyseo.org/analytics/overview/?q={dom}&protocol=https&searchType=domain'})
    d = r.json()
    if 'error' in d:
        return {'domain': dom, 'error': d['error'].get('message')}
    rows = d.get('result') or []
    ru = next((x for x in rows if x.get('database') == 'ru'), {})
    return {'domain': dom,
            'ru_traffic': ru.get('organicTraffic'), 'ru_keywords': ru.get('organicPositions'),
            'ru_cost': ru.get('organicCost'),
            'all_traffic': sum(x.get('organicTraffic') or 0 for x in rows),
            'all_keywords': sum(x.get('organicPositions') or 0 for x in rows),
            'bases': len(rows)}


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    cookie = open(SP, encoding='utf-8').read().strip()
    out = []
    with httpx.Client(timeout=90) as c:
        for d in doms:
            r = summary(c, cookie, d)
            out.append(r)
            print(f"  {d:24} ru: трафик {str(r.get('ru_traffic')):>6} ключей {str(r.get('ru_keywords')):>6}"
                  f" | всего {str(r.get('all_traffic')):>7}" + (f"  [{r.get('error')}]" if r.get('error') else ''),
                  flush=True)
            time.sleep(1)
    json.dump(out, open('semrush-donors.json', 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
