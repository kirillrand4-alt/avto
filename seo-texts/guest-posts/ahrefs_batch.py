#!/usr/bin/env python3
"""UR страниц размещений через Batch Analysis групбай-аккаунта владельца.

Эндпоинт снят с живого запроса панели (`/v4/baTable`): POST JSON с массивом targets
до 500 штук за раз, один такой запрос стоит ОДНУ единицу лимита - поэтому режем
ровно по 500, а не мельче.

    PROVIDER-независимый скрипт; куки берутся из файла вне репозитория.
    GBS_COOKIE_FILE=... python3 ahrefs_batch.py ahrefs-targets.json

Ответ приходит в форме ["Ok", {"rows":[...]}], значения полей - ["Some", v] либо "None".
Результат дописывается в ahrefs-ur.jsonl с fsync: JWT живёт 30 минут, и прогон
почти наверняка переживёт не одну смену куки.
"""
import json, os, sys, time
import httpx

SP = os.environ.get('GBS_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1/scratchpad/gbs_cookie.txt')
URL = 'https://ahrefs.groupbuyseo.org/v4/baTable'
OUT = 'ahrefs-ur.jsonl'
HDR = {
    'content-type': 'application/json; charset=utf-8',
    'accept': '*/*',
    'origin': 'https://ahrefs.groupbuyseo.org',
    'referer': 'https://ahrefs.groupbuyseo.org/batch-analysis/report?country=all&limit=50&offset=0',
    'x-client-version': 'release-20260818-bk31634-e3be9b3dd73d6',
    'user-agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'),
}


def val(v):
    """Поля приходят как ["Some", значение] либо строкой "None"."""
    if isinstance(v, list) and len(v) == 2 and v[0] == 'Some':
        return v[1]
    return None


def main():
    targets = json.load(open(sys.argv[1], encoding='utf-8'))
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            if line.strip():
                done.add(json.loads(line)['url'])
    todo = [u for u in targets if u not in done]
    print(f'целей: {len(targets)} | уже есть: {len(done)} | к запросу: {len(todo)}', flush=True)

    cookie = open(SP, encoding='utf-8').read().strip()
    out = open(OUT, 'a', encoding='utf-8')
    with httpx.Client(timeout=180, headers=HDR, cookies=None) as c:
        for i in range(0, len(todo), 500):
            chunk = todo[i:i + 500]
            body = {'targets': [{'target': u, 'mode': 'exact', 'protocol': 'both'} for u in chunk],
                    'filter': {'volumeMode': 'monthly'}}
            r = c.post(URL, content=json.dumps(body), headers={'cookie': cookie})
            if r.status_code != 200:
                print(f'батч {i//500+1}: HTTP {r.status_code} - {r.text[:200]}', flush=True)
                return 1
            data = r.json()
            if not (isinstance(data, list) and data[0] == 'Ok'):
                print(f'батч {i//500+1}: неожиданный ответ {str(data)[:200]}', flush=True)
                return 1
            rows = data[1].get('rows', [])
            for row, u in zip(rows, chunk):
                out.write(json.dumps({'url': u, 'ur': val(row.get('ur')), 'dr': val(row.get('dr')),
                                      'traffic': val(row.get('org_traffic')),
                                      'backlinks': val(row.get('backlinks')),
                                      'refdomains': val(row.get('refdomains'))},
                                     ensure_ascii=False) + '\n')
            out.flush(); os.fsync(out.fileno())
            got = sum(1 for r_ in rows if val(r_.get('ur')) is not None)
            print(f'батч {i//500+1}: строк {len(rows)}, с UR {got}', flush=True)
            if i + 500 < len(todo):
                time.sleep(2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
