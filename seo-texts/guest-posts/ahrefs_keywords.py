#!/usr/bin/env python3
"""Семантика доноров: по каким запросам их реально находят.

Владелец 18.08: «ты семантическую близость по ним проверил уже?» - нет, и это
оказалось решающим. Тематику я брал из колонки выгрузки биржи, а трафик приходит
совсем по другим запросам. priazovstep.ru числится аграрной газетой, а его 6442
российских посетителя ищут «троица 2026» и «11 мая выходной или нет».

Эндпоинт seGetOrganicKeywords снят с живого запроса панели; shape урезан до
нужного: текст запроса, страна, объём, трафик, позиция.

    python3 ahrefs_keywords.py donors.txt [размер выборки]
"""
import json, os, sys, time, urllib.parse
import httpx

SP = os.environ.get('GBS_COOKIE_FILE',
                    '/tmp/claude-0/-home-user-avto/20e1aa6d-1000-514f-959c-428ea037ecc1/scratchpad/gbs_cookie.txt')
BASE = 'https://ahrefs.groupbuyseo.org/v4/seGetOrganicKeywords'
OUT = os.environ.get('KW_OUT', 'ahrefs-keywords.jsonl')
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36')

_M = lambda p: {'field_name': ['Direct', {'field': ['KeywordsCompared', 'MergedKeyword', p],
                                          'modifier': None}], 'alias': None}
_C = lambda p: {'field_name': ['Direct', {'field': ['KeywordsCompared', 'CurrentKeyword', p],
                                          'modifier': None}], 'alias': None}


def payload(dom, size):
    t = dom.rstrip('/') + '/'
    return {'args': {'mode': 'subdomains', 'protocol': 'both', 'url': t,
                     'multiTarget': ['Single', {'target': t, 'mode': 'subdomains',
                                                'protocol': 'both'}],
                     'reportMode': ['Compared', {'actual': 'Today',
                                                 'comparedWith': ['Ago', 'Month3']}],
                     'groupBy': 'location'},
            'params': {'size': size, 'offset': 0,
                       'order_by': [['Desc', ['Direct', {'field': ['KeywordsCompared',
                                                                   'MergedKeyword', 'traffic'],
                                                         'modifier': None}]]],
                       'shape': [_M('text'), _M('country'), _M('volume'), _M('traffic'),
                                 _C('best_position')]}}


def main():
    doms = [l.strip() for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    # Глубина решает: у metallicheckiy-portal.ru в топ-60 по трафику промышленных
    # запросов НЕТ вовсе, при size=500 их семь, при size=2000 - шестьдесят. Они дают
    # по 5-13 посетителей каждый и в верхушку не попадают, хотя именно они говорят,
    # что площадка отраслевая (поправка владельца 18.08).
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            if not line.strip():
                continue
            rec = json.loads(line)
            # Домен с ошибкой сделанным НЕ считаем: обрывы на тяжёлых ответах временные,
            # при повторе тот же домен отдаётся нормально. Иначе повторный запуск
            # молча пропускал бы всё, что упало.
            if not rec.get('error'):
                done.add(rec['domain'])
    todo = [d for d in doms if d not in done]
    print(f'доменов: {len(doms)} | уже есть: {len(done)} | к запросу: {len(todo)}', flush=True)
    cookie = open(SP, encoding='utf-8').read().strip()
    out = open(OUT, 'a', encoding='utf-8')
    hdr = {'x-client-version': 'release-20260819-bk32024-c3b15038be652', 'user-agent': UA,
           'accept': '*/*', 'cookie': cookie}
    with httpx.Client(timeout=120, headers=hdr) as c:
        for i, d in enumerate(todo, 1):
            url = BASE + '?input=' + urllib.parse.quote(json.dumps(payload(d, size),
                                                                   ensure_ascii=False))
            try:
                r = c.get(url, headers={'referer': f'https://ahrefs.groupbuyseo.org/'
                                                   f'site-explorer/organic-keywords?target={d}'})
                data = r.json()
            except Exception as e:                           # noqa: BLE001
                out.write(json.dumps({'domain': d, 'error': repr(e)[:120]}, ensure_ascii=False) + '\n')
                out.flush(); continue
            if not (isinstance(data, list) and data[0] == 'Ok'):
                out.write(json.dumps({'domain': d, 'error': str(data)[:150]}, ensure_ascii=False) + '\n')
                out.flush(); os.fsync(out.fileno())
                print(f'  {d:26} ошибка {str(data)[:80]}', flush=True)
                continue
            rows = data[1].get('rows', [])
            kws = [{'kw': x[0], 'country': x[1], 'volume': x[2], 'traffic': x[3], 'pos': x[4]}
                   for x in rows]
            out.write(json.dumps({'domain': d, 'n': len(kws), 'keywords': kws},
                                 ensure_ascii=False) + '\n')
            out.flush(); os.fsync(out.fileno())
            if i % 25 == 0 or i < 4:
                top = ', '.join(k['kw'] for k in kws[:3])
                print(f'  [{i}/{len(todo)}] {d:24} {len(kws):>3} запросов | {top[:70]}', flush=True)
            time.sleep(0.4)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
