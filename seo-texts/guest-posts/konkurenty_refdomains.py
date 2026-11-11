#!/usr/bin/env python3
"""Кто ссылается на конкурентов: поиск отраслевых изданий через Ahrefs Referring domains.

    python3 konkurenty_refdomains.py домен1 домен2 ...   -> konkurenty-refdomains.jsonl

Тело запроса - ahrefs-refdomains-body.json, снято владельцем из браузера 10.11.2026
(отчёт Site Explorer -> Referring domains, эндпоинт /v4/seRefdomains). Цель подменяется,
страницы по 100 доменов, до LIMIT на конкурента. Сессия групбая продлевается gbs_refresh.
Идея: сайт, ссылающийся на нескольких конкурентов сразу, - отраслевая площадка.
"""
import copy
import json
import os
import sys

import httpx

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import ahrefs_domains as AD  # noqa: E402
import gbs_refresh  # noqa: E402

URL = 'https://ahrefs.groupbuyseo.org/v4/seRefdomains'
BODY = json.load(open(os.path.join(DIR, 'ahrefs-refdomains-body.json'), encoding='utf-8'))
OUT = os.path.join(DIR, 'konkurenty-refdomains.jsonl')
LIMIT = int(os.environ.get('RD_LIMIT', '500'))
# Размер страницы: просим сразу до 500 за запрос (лимит Ahrefs считается по запросам).
# Если сервер режет страницу (вернул ровно 100 вместо 500), переходим на его размер.
PAGE = int(os.environ.get('RD_PAGE', '500'))
HDR = {**AD.HDR, 'x-client-version': 'release-20261110-bk61752-b13230aaa10f8',
       'x-should-be-get': 'true',
       'referer': 'https://ahrefs.groupbuyseo.org/site-explorer/refdomains'}


def body_for(target, offset, size):
    b = copy.deepcopy(BODY)
    t = target.rstrip('/') + '/'
    b['se_params']['target'] = t
    b['se_params']['multiTarget'] = ['Single', {'target': t, 'mode': 'subdomains', 'protocol': 'both'}]
    b['se_params'].pop('since', None)
    b['se_params']['history_mode'] = 'Live'
    b['params']['offset'] = offset
    b['params']['size'] = size
    b['backlinks_params']['size'] = 1     # нужны домены, а не сами ссылки
    return b


def fetch(c, target):
    out, off, page = [], 0, PAGE
    while off < LIMIT:
        size = min(page, LIMIT - off)
        r = c.post(URL, content=json.dumps(body_for(target, off, size)))
        d = r.json()
        if not (isinstance(d, list) and d[0] == 'Ok'):
            raise RuntimeError(f'{target}: {str(d)[:200]}')
        rows = d[1].get('rows') or d[1].get('refdomains') or []
        out.extend(rows)
        if len(rows) < size and len(rows) in (100, 200, 250) and page > len(rows):
            page = len(rows)              # сервер режет страницу - листаем его размером
            print(f'{target}: сервер отдаёт по {page} за запрос', flush=True)
        elif len(rows) < size:
            break
        off += len(rows)
    return out


def main():
    gbs_refresh.refresh(AD.SP)
    ck = open(AD.SP, encoding='utf-8').read().strip()
    with httpx.Client(timeout=120, headers={**HDR, 'cookie': ck}) as c, open(OUT, 'a', encoding='utf-8') as f:
        for t in sys.argv[1:]:
            rows = fetch(c, t)
            f.write(json.dumps({'target': t, 'rows': rows}, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
            print(f'{t}: доменов {len(rows)}', flush=True)


if __name__ == '__main__':
    main()
