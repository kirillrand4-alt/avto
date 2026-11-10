#!/usr/bin/env python3
"""Купленные статьи прошлой кампании глазами Ahrefs и Semrush, по каждой странице.

    python3 kuplennye_check.py <SSYLKI-MIRALINKS-VLIYANIE.csv>  -> kuplennye-check.json

Ahrefs: Batch Analysis в режиме exact (сама страница статьи): UR, органика, ключи,
ссылающиеся домены. Semrush: organic.Summary с searchType=url, база ru.
Вопрос: получают ли купленные статьи хоть какой-то трафик из поиска, и сходятся ли
сервисы на уровне отдельной страницы.
"""
import csv
import json
import os
import sys

import httpx

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import ahrefs_domains as AD  # noqa: E402
import gbs_refresh  # noqa: E402
import semrush_check as SR  # noqa: E402

OUT = os.path.join(DIR, 'kuplennye-check.json')


def ahrefs(urls):
    gbs_refresh.refresh(AD.SP)
    ck = open(AD.SP, encoding='utf-8').read().strip()
    body = {'targets': [{'target': u, 'mode': 'exact', 'protocol': 'both'} for u in urls],
            'filter': {'volumeMode': 'monthly'}}
    r = httpx.post(AD.URL, content=json.dumps(body), headers={**AD.HDR, 'cookie': ck}, timeout=300)
    data = r.json()
    if not (isinstance(data, list) and data[0] == 'Ok'):
        raise SystemExit(f'Ahrefs: {str(data)[:200]}')
    out = {}
    for row, u in zip(data[1]['rows'], urls):
        out[u] = {f: AD.val(row.get(f)) for f in ('ur', 'org_traffic', 'org_keywords', 'refdomains')}
    return out


def semrush(urls):
    ck = open(AD.SP, encoding='utf-8').read().strip()
    out = {}
    with httpx.Client(timeout=60) as c:
        for u in urls:
            body = {'id': 1, 'jsonrpc': '2.0', 'method': 'organic.Summary',
                    'params': {'request_id': 'x1', 'report': 'domain.overview',
                               'userId': SR.UID, 'apiKey': SR.API,
                               'args': {'database': 'ru', 'searchItem': u,
                                        'searchType': 'url', 'dateType': 'monthly'}}}
            r = c.post(SR.URL, content=json.dumps(body), headers={
                'cookie': ck, 'content-type': 'application/json; charset=utf-8',
                'user-agent': SR.UA, 'origin': 'https://sr.groupbuyseo.org'})
            d = r.json()
            if 'error' in d:
                out[u] = {'error': d['error'].get('message')}
                continue
            rows = d.get('result') or []
            ru = next((x for x in rows if x.get('database') == 'ru'), {})
            out[u] = {'ru_traffic': ru.get('organicTraffic'), 'ru_keywords': ru.get('organicPositions'),
                      'all_traffic': sum(x.get('organicTraffic') or 0 for x in rows)}
    return out


def main():
    rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8-sig'), delimiter=';'))
    placed = [r for r in rows if r['статус'] == 'размещена' and r['URL донора'].startswith('http')]
    urls = sorted({r['URL донора'] for r in placed})
    a, s = ahrefs(urls), semrush(urls)
    res = []
    for u in urls:
        r0 = next(r for r in placed if r['URL донора'] == u)
        res.append({'url': u, 'donor': r0['донор'], 'date': r0['дата размещения'],
                    'ahrefs': a.get(u), 'semrush': s.get(u)})
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    for x in res:
        print(f"{x['date']} {x['donor']:24s} UR {x['ahrefs'].get('ur')} | Ahrefs трафик "
              f"{x['ahrefs'].get('org_traffic')} ключей {x['ahrefs'].get('org_keywords')} | Semrush "
              f"{x['semrush'].get('ru_traffic', x['semrush'].get('error'))} ключей {x['semrush'].get('ru_keywords')}")


if __name__ == '__main__':
    main()
