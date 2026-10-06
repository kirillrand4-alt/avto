# -*- coding: utf-8 -*-
"""Проверка идей запросов (idei_zaprosy.csv) на сервере: выдача IDEI-SERP.jsonl → главные страницы
(кэш пилота sayty.jsonl + idei-sayty.jsonl) → по каждому запросу: профильные, новые для базы,
новые и для базы, и для пилота. Итог: IDEI-TEST.csv и IDEI-DOMENY.csv на drop."""
import csv
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import obrabotka as O  # noqa: E402
import analiz as A  # noqa: E402

SERP = os.path.join(A.OUT, 'IDEI-SERP.jsonl')
CACHE = os.path.join(A.OUT, 'idei-sayty.jsonl')


def rows():
    for line in open(SERP, encoding='utf-8'):
        j = json.loads(line)
        for d in j.get('docs') or []:
            yield {'engine': j['engine'], 'query': j['query'], 'segment': j['segment'],
                   'subsegment': j['subsegment'], 'region': j['region'], 'qid': j['qid'], **d}


def main():
    stop, post = O.load_stop(os.path.join(D, '..', 'stop_domeny.txt')), O.load_post(os.path.join(D, '..', 'minus_slova.txt'))
    cands, _, _ = O.aggregate(rows(), stop, post)
    # порталы в тесте не считаем (выборка мала): возвращаем всё, кроме стоп-листа
    sayty = {}
    for p in (A.SAYTY, CACHE):
        if os.path.exists(p):
            for l in open(p, encoding='utf-8'):
                j = json.loads(l)
                sayty[j['domain']] = j
    pilot_cands = set()
    for line in open(A.SERP, encoding='utf-8'):
        for d in json.loads(line).get('docs') or []:
            pilot_cands.add(O.norm_domain(d['url']))
    todo = [c for d, c in cands.items() if d not in sayty]
    with open(CACHE, 'a', encoding='utf-8') as f, ThreadPoolExecutor(16) as ex:
        for rec in ex.map(A.proverit, todo):
            sayty[rec['domain']] = rec
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    et = json.load(open(A.ETALON, encoding='utf-8'))
    kd, ki = set(et['domains']), set(et['inns'])
    dom_rows, info = [], {}
    for d, c in cands.items():
        s = sayty.get(d, {})
        alive = bool(s.get('http_status')) and s['http_status'] < 400
        segs = sorted(c['segments'])
        best = max((s.get('scores') or {}).get(x, -99) for x in segs) if alive else None
        tip = O.tip_sayta(s.get('title') or (c['titles'][0] if c['titles'] else ''), d) if alive else ''
        prof = alive and not s.get('is_parked') and best is not None and best >= O.POROG and not tip
        ids = (s.get('inn') or []) + (s.get('unp') or [])
        st = O.status(d if d in kd else (s.get('final_domain') or d), ids, kd, ki) if prof else ''
        info[d] = (prof, st, d not in pilot_cands)
        dom_rows.append({'domain': O.domain_unicode(d), 'segments': '|'.join(segs), 'engines': '|'.join(sorted(c['engines'])),
                         'tip': tip, 'profile_score': best, 'status': st, 'new_vs_pilot': int(d not in pilot_cands),
                         'inn': '|'.join(s.get('inn') or []), 'unp': '|'.join(s.get('unp') or []),
                         'title': s.get('title') or (c['titles'][0] if c['titles'] else '')})
    q2d = defaultdict(set)
    qmeta = {}
    for r in rows():
        qmeta[r['query']] = (r['qid'], r['segment'])
        dd = O.norm_domain(r['url'])
        if dd in cands:
            q2d[r['query']].add(dd)
    out = []
    for q, (qid, seg) in sorted(qmeta.items(), key=lambda kv: kv[1]):
        ds = q2d[q]
        prof = [d for d in ds if info[d][0]]
        new = [d for d in prof if info[d][1].startswith('new')]
        novel = [d for d in new if info[d][2]]
        out.append({'qid': qid, 'segment': seg, 'query': q, 'domains': len(ds), 'profile': len(prof),
                    'new_vs_base': len(new), 'new_vs_base_and_pilot': len(novel),
                    'examples': ' '.join(O.domain_unicode(d) for d in novel[:5])})
    for name, data in (('IDEI-TEST.csv', out), ('IDEI-DOMENY.csv', dom_rows)):
        with open(os.path.join(A.DROP, name), 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            w.writeheader(); w.writerows(data)
    tot = lambda k: sum(o[k] for o in out)
    uniq_novel = {d for d, v in info.items() if v[0] and v[1].startswith('new') and v[2]}
    print('===ИТОГ===')
    print(json.dumps({'zaprosov': len(out), 'kandidatov': len(cands), 'provereno_novyh_saytov': len(todo),
                      'profilnyh': sum(1 for v in info.values() if v[0]),
                      'novyh_dlya_bazy': sum(1 for v in info.values() if v[0] and v[1].startswith('new')),
                      'novyh_i_dlya_pilota': len(uniq_novel),
                      'sum_po_zaprosam': {k: tot(k) for k in ('profile', 'new_vs_base', 'new_vs_base_and_pilot')}},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
