#!/usr/bin/env python3
"""Позиции доноров в Google RU (Semrush organic.Positions: запрос + URL + трафик, до 500 строк).

    GBS_COOKIE_FILE=... SR_TREND_KEY=... SR_UID=... python3 donory_pozicii.py domains.txt
    -> donory-pozicii.jsonl

Для принципов 2 (получают ли статьи на доноре трафик) и 3 (доля промышленных запросов).
Аккаунт Semrush задаётся cookie (PHPSESSID/SSO-JWT) + userId/apiKey из запроса панели.
Резюмируется, пишет с fsync.
"""
import json
import os
import sys
import time

import httpx

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import semrush_check as SR  # noqa: E402

CK = os.environ['GBS_COOKIE_FILE']
OUT = os.path.join(DIR, 'donory-pozicii.jsonl')
KEY, UID = os.environ['SR_TREND_KEY'], int(os.environ['SR_UID'])
SIZE = int(os.environ.get('POS_SIZE', '500'))


def positions(c, dom):
    a = {'database': 'ru', 'searchItem': dom, 'searchType': 'domain', 'dateFormat': 'date', 'dateType': 'daily',
         'filter': {}, 'positionsType': 'all',
         'display': {'page': 1, 'pageSize': SIZE, 'order': {'field': 'traffic', 'direction': 'desc'}}}
    b = {'id': 1, 'jsonrpc': '2.0', 'method': 'organic.Positions',
         'params': {'request_id': 'x', 'report': 'organic.positions', 'args': a, 'userId': UID, 'apiKey': KEY}}
    return c.post(SR.URL, content=json.dumps(b), headers={
        'cookie': open(CK, encoding='utf-8').read().strip(), 'content-type': 'application/json; charset=utf-8',
        'user-agent': SR.UA, 'origin': 'https://sr.groupbuyseo.org',
        'referer': 'https://sr.groupbuyseo.org/analytics/organic/positions/'}).json()


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)['domain'] for l in open(OUT, encoding='utf-8') if '"error"' not in l}
    todo = [d for d in doms if d not in done]
    print(f'всего {len(doms)}, есть {len(done)}, к запросу {len(todo)}', flush=True)
    with httpx.Client(timeout=120) as c, open(OUT, 'a', encoding='utf-8') as f:
        for i, d in enumerate(todo, 1):
            try:
                r = positions(c, d)
                if r.get('error'):
                    rec = {'domain': d, 'error': r['error'].get('message')}
                else:
                    rec = {'domain': d, 'rows': [[x.get('phrase'), x.get('url'), x.get('traffic'), x.get('position'),
                                                  x.get('volume')] for x in r.get('result') or []]}
            except Exception as e:  # noqa: BLE001
                rec = {'domain': d, 'error': repr(e)[:120]}
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            print(i, d, len(rec.get('rows') or []) if 'rows' in rec else rec['error'], flush=True)
            if 'limit' in str(rec.get('error', '')).lower():
                break
            time.sleep(0.5)


if __name__ == '__main__':
    main()
