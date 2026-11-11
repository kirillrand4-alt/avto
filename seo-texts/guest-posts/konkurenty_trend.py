#!/usr/bin/env python3
"""Помесячная история органики конкурентов из Semrush (база ru = Google RU).

    python3 konkurenty_trend.py domains.txt   -> konkurenty-trend.jsonl

Метод organic.OverviewTrend (отчёт domain.overview), dateType=monthly: один запрос
даёт всю историю с 2012 г. Нужен для вопроса «помогли ли конкурентам ссылки»:
сопоставляем с first_seen ссылающихся доменов из konkurenty-refdomains.jsonl.
Резюмируется: уже собранные домены пропускаются. Пишем с fsync.
"""
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import semrush_check as SR  # noqa: E402

CK = os.environ.get('GBS_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1/scratchpad/gbs_panel.txt')
OUT = os.path.join(DIR, 'konkurenty-trend.jsonl')
KEY = os.environ.get('SR_TREND_KEY') or SR.API
UID = int(os.environ.get('SR_UID') or SR.UID)
SERVERS = [int(x) for x in os.environ.get('SR_SERVERS', '1924,1925,1926,2578,2579').split(',')]
_si = [0]
KEEP = ('date', 'organicTraffic', 'organicTrafficNonBranded', 'organicPositions', 'rank')


def _cookie(srv):
    base = open(CK, encoding='utf-8').read().strip()
    return re.sub(r'user_servers=\{[^}]*\}', 'user_servers={"Ahrefs":2596,"Semrush":%d}' % srv, base)


def trend(c, dom, srv=None):
    ck = _cookie(srv or SERVERS[_si[0] % len(SERVERS)])
    a = {'database': 'ru', 'dateFormat': 'date', 'dateType': 'monthly', 'searchItem': dom, 'searchType': 'domain'}
    b = {'id': 1, 'jsonrpc': '2.0', 'method': 'organic.OverviewTrend',
         'params': {'request_id': 'x', 'report': 'domain.overview', 'args': a, 'userId': UID, 'apiKey': KEY}}
    r = c.post(SR.URL, content=json.dumps(b), headers={
        'cookie': ck, 'content-type': 'application/json; charset=utf-8', 'user-agent': SR.UA,
        'origin': 'https://sr.groupbuyseo.org', 'referer': 'https://sr.groupbuyseo.org/analytics/overview/'})
    j = r.json()
    if j.get('error'):
        return {'domain': dom, 'error': j['error'].get('message')}
    return {'domain': dom, 'm': [[x.get(k) for k in KEEP] for x in j['result']]}


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
    with httpx.Client(timeout=90) as c, open(OUT, 'a', encoding='utf-8') as f, ThreadPoolExecutor(2) as ex:
        for i, rec in enumerate(ex.map(lambda d: _safe(c, d), todo), 1):
            f.write(json.dumps(rec, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
            if rec.get('error') or i % 25 == 0:
                print(i, rec['domain'], rec.get('error', 'ok'), flush=True)


def _safe(c, d):
    try:
        for _ in range(len(SERVERS)):
            rec = trend(c, d)
            if 'limit' not in (rec.get('error') or '').lower():
                return rec
            _si[0] += 1  # сервер выбрал лимит отчётов - следующий
        return rec
    except Exception as e:  # noqa: BLE001
        return {'domain': d, 'error': repr(e)[:120]}


if __name__ == '__main__':
    main()
