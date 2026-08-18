#!/usr/bin/env python3
"""Органика доноров по ДОМЕНАМ через тот же baTable, что и UR страниц.

Владелец 18.08: «может по ахрефсу сначала органику и смотреть?» - да, и это
надо было делать с самого начала. baTable отдаёт на каждую цель тридцать полей,
включая org_traffic, org_keywords и разбивку по позициям; я запрашивал их
15 335 раз для страниц и сохранял из них пять, причём органику терял (у страницы
в режиме exact она почти всегда null).

Здесь цель - домен, а не страница: mode=domain. Тысяча доменов = три запроса
из лимита в 1000. Semrush с его суточным лимитом на отчёты для этого не нужен.

    python3 ahrefs_domains.py donors.txt
"""
import json, os, sys, time
import httpx

SP = os.environ.get('GBS_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1/scratchpad/gbs_cookie.txt')
URL = 'https://ahrefs.groupbuyseo.org/v4/baTable'
OUT = 'ahrefs-domains.jsonl'
HDR = {'content-type': 'application/json; charset=utf-8', 'accept': '*/*',
       'origin': 'https://ahrefs.groupbuyseo.org',
       'referer': 'https://ahrefs.groupbuyseo.org/batch-analysis/report?country=all&limit=50&offset=0',
       'x-client-version': 'release-20260818-bk31725-fcee48cb67108',
       'user-agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36')}
FIELDS = ['dr', 'ar', 'ur', 'org_keywords', 'org_top_1_3_keywords', 'org_top_4_10_keywords',
          'org_top_11_20_keywords', 'org_top_21_50_keywords', 'org_traffic', 'org_value',
          'backlinks', 'backlinks_dofollow', 'refdomains', 'refdomains_dofollow',
          'linked_domains']


def val(v):
    return v[1] if isinstance(v, list) and len(v) == 2 and v[0] == 'Some' else None


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            if line.strip():
                done.add(json.loads(line)['domain'])
    todo = [d for d in doms if d not in done]
    print(f'доменов: {len(doms)} | уже есть: {len(done)} | к запросу: {len(todo)} '
          f'({(len(todo)+499)//500} батчей)', flush=True)
    cookie = open(SP, encoding='utf-8').read().strip()
    out = open(OUT, 'a', encoding='utf-8')
    with httpx.Client(timeout=300, headers=HDR) as c:
        for i in range(0, len(todo), 500):
            chunk = todo[i:i + 500]
            body = {'targets': [{'target': d, 'mode': 'domain', 'protocol': 'both'} for d in chunk],
                    'filter': {'volumeMode': 'monthly'}}
            r = c.post(URL, content=json.dumps(body), headers={'cookie': cookie})
            if r.status_code != 200:
                print(f'батч {i//500+1}: HTTP {r.status_code} {r.text[:150]}'); return 1
            data = r.json()
            if not (isinstance(data, list) and data[0] == 'Ok'):
                print(f'батч {i//500+1}: {str(data)[:200]}'); return 1
            rows = data[1].get('rows', [])
            for row, d in zip(rows, chunk):
                rec = {'domain': d}
                rec.update({f: val(row.get(f)) for f in FIELDS})
                by = row.get('org_traffic_top_by_country') or []
                rec['country_top'] = by[:4]
                rec['ru_share'] = next((n for cc, n in by if cc == 'ru'), 0)
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
            out.flush(); os.fsync(out.fileno())
            live = sum(1 for r_ in rows if (val(r_.get('org_traffic')) or 0) > 100)
            print(f'батч {i//500+1}: {len(rows)} доменов, с органикой >100: {live}', flush=True)
            if i + 500 < len(todo):
                time.sleep(3)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
