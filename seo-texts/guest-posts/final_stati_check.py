#!/usr/bin/env python3
"""Трафик статей финалистов в Ahrefs (режим prefix) с контрольными страницами.

    GBS_COOKIE_FILE=... python3 final_stati_check.py   -> final-1110-ahrefs-stati.json

Контроль: страницы, у которых трафик точно есть. Если Ahrefs и им отдаст ноль, значит
трафик отдельных страниц в batch-отчёте не отдаётся, и нули статей ничего не значат.
"""
import collections
import json
import os
import sys
import urllib.parse

import httpx

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)
import ahrefs_domains as AD  # noqa: E402
import gbs_refresh  # noqa: E402

CTRL = ['https://prokompressor.ru/catalog/osushiteli/',
        'https://ru.wikipedia.org/wiki/' + urllib.parse.quote('Компрессор'),
        'https://www.drive2.ru/o/b/673745267324885925/']
EXTRA = ['https://metaprom.ru/news/biznes-finansy/20-07-26-n4722/']


def main():
    gbs_refresh.refresh(AD.SP)
    ck = open(AD.SP, encoding='utf-8').read().strip()
    urls = [l.strip() for l in open(os.path.join(DIR, 'final-1110-urls.txt'), encoding='utf-8') if l.strip()]
    allu = CTRL + EXTRA + urls
    out = {}
    for i in range(0, len(allu), 100):   # с 11.11 Ahrefs режет пакет больше ~100-300 целей (TargetsLimitReached)
        ch = allu[i:i + 100]
        body = {'targets': [{'target': u, 'mode': 'prefix', 'protocol': 'both'} for u in ch],
                'filter': {'volumeMode': 'monthly'}}
        r = httpx.post(AD.URL, content=json.dumps(body), headers={**AD.HDR, 'cookie': ck}, timeout=300)
        d = r.json()
        if d[0] != 'Ok':
            raise SystemExit(f'Ahrefs: {d}')
        for row, u in zip(d[1]['rows'], ch):
            out[u] = {k: AD.val(row.get(f)) for k, f in
                      (('ur', 'ur'), ('tr', 'org_traffic'), ('kw', 'org_keywords'), ('rd', 'refdomains'))}
    with open(os.path.join(DIR, 'final-1110-ahrefs-stati.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
        f.flush()
        os.fsync(f.fileno())
    for u in CTRL + EXTRA:
        print('контроль/доп', u[:70], out[u])
    by = collections.defaultdict(list)
    for u in urls:
        by[urllib.parse.urlparse(u).netloc.replace('www.', '')].append(out[u])
    print('площадка | статей | с трафиком | медиана | с ключами | UR>0')
    for dom, v in by.items():
        tr = sorted(int(x['tr'] or 0) for x in v)
        print(dom, len(v), sum(t > 0 for t in tr), tr[len(tr) // 2],
              sum(int(x['kw'] or 0) > 0 for x in v), sum((x['ur'] or 0) > 0 for x in v))


if __name__ == '__main__':
    main()
