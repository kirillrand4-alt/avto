#!/usr/bin/env python3
"""Top Pages доноров в Google RU (Semrush organic.Pages, 1 запрос = до 500 страниц).

    python3 donory_pages.py domains.txt   -> donory-pages.jsonl

Нужен, чтобы проверить: получают ли статьи на доноре поисковый трафик, и какая
доля трафика донора тематическая. organic.Positions с ключом панели отвечает
«Sorting is denied», а Pages работает. Перебор серверов на «Report limits exceeded».
Резюмируется, пишет с fsync.
"""
import json
import os
import re
import sys
import time

import httpx

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import semrush_check as SR  # noqa: E402

CK = os.environ.get('GBS_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1/scratchpad/gbs_panel.txt')
OUT = os.path.join(DIR, 'donory-pages.jsonl')
KEY = os.environ.get('SR_TREND_KEY') or SR.API
UID = int(os.environ.get('SR_UID') or SR.UID)
SERVERS = [int(x) for x in os.environ.get(
    'SR_SERVERS', '1003,1141,1146,1154,1923,1924,1925,1926,2578,2579').split(',')]
SIZE = int(os.environ.get('PAGES_SIZE', '500'))


def pages(c, dom, srv):
    base = open(CK, encoding='utf-8').read().strip()
    ck = re.sub(r'user_servers=\{[^}]*\}', 'user_servers={"Ahrefs":2581,"Semrush":%d}' % srv, base)
    a = {'database': 'ru', 'searchItem': dom, 'searchType': 'domain', 'dateFormat': 'date', 'dateType': 'daily',
         'filter': {}, 'display': {'page': 1, 'pageSize': SIZE, 'order': {'field': 'traffic', 'direction': 'desc'}}}
    b = {'id': 1, 'jsonrpc': '2.0', 'method': 'organic.Pages',
         'params': {'request_id': 'x', 'report': 'organic.pages', 'args': a, 'userId': UID, 'apiKey': KEY}}
    return c.post(SR.URL, content=json.dumps(b), headers={
        'cookie': ck, 'content-type': 'application/json; charset=utf-8', 'user-agent': SR.UA,
        'origin': 'https://sr.groupbuyseo.org', 'referer': 'https://sr.groupbuyseo.org/analytics/organic/pages/'}).json()


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            d = json.loads(l)
            if not d.get('error'):
                done.add(d['domain'])
    todo = [d for d in doms if d not in done]
    print(f'всего {len(doms)}, есть {len(done)}, к запросу {len(todo)}', flush=True)
    si = 0
    with httpx.Client(timeout=120) as c, open(OUT, 'a', encoding='utf-8') as f:
        for i, d in enumerate(todo, 1):
            rec = None
            for _ in range(len(SERVERS)):
                try:
                    r = pages(c, d, SERVERS[si])
                except Exception as e:  # noqa: BLE001
                    rec = {'domain': d, 'error': repr(e)[:120]}
                    break
                err = (r.get('error') or {}).get('message')
                if err and 'limit' in err.lower():
                    si = (si + 1) % len(SERVERS)
                    continue
                if err:
                    rec = {'domain': d, 'error': err}
                    break
                rows = r.get('result') or []
                rec = {'domain': d, 'pages': [{'url': x.get('url'), 'traffic': x.get('traffic'),
                                               'kw': x.get('positions') or x.get('keywords'),
                                               'top_kw': x.get('topKeyword') or x.get('keyword')} for x in rows]}
                break
            rec = rec or {'domain': d, 'error': 'лимит на всех серверах'}
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            print(i, d, len(rec.get('pages') or []) if 'pages' in rec else rec['error'], flush=True)
            time.sleep(0.3)


if __name__ == '__main__':
    main()
