#!/usr/bin/env python3
"""Ключевые запросы домена через Semrush групбая - замена ahrefs_keywords.py, когда
у Ahrefs кончился дневной лимит.

    python3 semrush_keywords.py domains.txt [сколько запросов на домен]   -> KW_OUT

Метод organic.Positions (отчёт organic.positions), вид аргументов снят с живого
запроса панели 10.11.2026: обязателен positionsType и блок display с page/pageSize/
order, без них «Invalid params». Выход в формате ahrefs_keywords.py
({domain, n, keywords:[{kw, country, volume, traffic, pos}]}), поэтому
classify_semantic.py читает его без переделок.

Сервер Semrush выбирается cookie user_servers; ключи из SR_KEYS_FILE принимаются
на любом сервере, отличается только лимит отчётов. На «Report limits exceeded»
переключаемся на следующий сервер.
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
OUT = os.environ.get('KW_OUT', 'semrush-keywords.jsonl')
SERVERS = [1003, 1141, 1146, 1154, 1923, 1924, 1925, 1926, 2578, 2579]
KEY = os.environ.get('SR_POS_KEY') or SR.API


def cookie(srv):
    base = open(CK, encoding='utf-8').read().strip()
    us = '{"Ahrefs":2596,"Semrush":%d}' % srv
    return re.sub(r'user_servers=\{[^}]*\}', 'user_servers=' + us, base) if 'user_servers=' in base \
        else base + '; user_servers=' + us


def positions(c, srv, dom, size):
    args = {'database': 'ru', 'searchItem': dom, 'searchType': 'domain', 'filter': {},
            'dateType': 'daily', 'positionsType': 'all',
            'display': {'page': 1, 'pageSize': size, 'order': {'field': 'traffic', 'direction': 'desc'}}}
    body = {'id': 1, 'jsonrpc': '2.0', 'method': 'organic.Positions',
            'params': {'request_id': 'x', 'report': 'organic.positions', 'args': args, 'apiKey': KEY}}
    r = c.post(SR.URL, content=json.dumps(body), headers={
        'cookie': cookie(srv), 'content-type': 'application/json; charset=utf-8', 'user-agent': SR.UA,
        'origin': 'https://sr.groupbuyseo.org',
        'referer': f'https://sr.groupbuyseo.org/analytics/organic/positions/?db=ru&q={dom}&searchType=domain'})
    return r.json()


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 500
    done = set()
    if os.path.exists(OUT):
        for l in open(OUT, encoding='utf-8'):
            if l.strip():
                d = json.loads(l)
                if not d.get('error'):
                    done.add(d['domain'])
    todo = [d for d in doms if d not in done]
    print(f'доменов: {len(doms)} | уже есть: {len(done)} | к запросу: {len(todo)}', flush=True)
    si = 0
    with httpx.Client(timeout=120) as c, open(OUT, 'a', encoding='utf-8') as f:
        for i, d in enumerate(todo, 1):
            rec = None
            for _ in range(len(SERVERS)):
                try:
                    res = positions(c, SERVERS[si], d, size)
                except Exception as e:  # noqa: BLE001
                    rec = {'domain': d, 'error': repr(e)[:120]}
                    break
                err = (res.get('error') or {}).get('message')
                if err and 'limit' in err.lower():
                    si = (si + 1) % len(SERVERS)
                    print(f'  лимит на сервере, переключаюсь на {SERVERS[si]}', flush=True)
                    continue
                if err:
                    rec = {'domain': d, 'error': err}
                    break
                rows = res.get('result') or []
                kws = [{'kw': x.get('phrase'), 'country': 'ru', 'volume': x.get('volume'),
                        'traffic': x.get('traffic'), 'pos': x.get('position')} for x in rows]
                rec = {'domain': d, 'n': len(kws), 'keywords': kws, 'src': 'semrush'}
                break
            rec = rec or {'domain': d, 'error': 'лимит на всех серверах'}
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            if i % 25 == 0 or i < 4 or rec.get('error'):
                top = ', '.join(k['kw'] for k in (rec.get('keywords') or [])[:3])
                print(f"  [{i}/{len(todo)}] {d:24} {rec.get('n', rec.get('error'))} | {top[:70]}", flush=True)
            time.sleep(0.3)


if __name__ == '__main__':
    main()
