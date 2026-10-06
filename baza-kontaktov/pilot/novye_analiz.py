# -*- coding: utf-8 -*-
"""Новые домены из источника: выдача (--serp FILE) или каталоги (--kat). Главные страницы — кэш
sayty.jsonl + idei-sayty.jsonl + novye-sayty.jsonl, недостающие докачиваются. Сверка с эталоном и со
всем, что уже находили (пилот, идеи, предыдущие источники).
    python novye_analiz.py --serp GLUBINA-SERP.jsonl [--name GLUBINA]
    python novye_analiz.py --kat
Выход на drop: NOVYE-<name>.csv (домены) + сводка в stdout."""
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import obrabotka as O  # noqa: E402
import analiz as A  # noqa: E402

CACHE = os.path.join(A.OUT, 'novye-sayty.jsonl')
SEGS = list(O.SLOVAR)


def arg(n, d=''):
    return sys.argv[sys.argv.index(n) + 1] if n in sys.argv else d


def serp_domains(path):
    seen = set()
    p = os.path.join(A.OUT, path)
    if not os.path.exists(p):
        return seen
    for line in open(p, encoding='utf-8'):
        for d in json.loads(line).get('docs') or []:
            seen.add(O.norm_domain(d['url']))
    return seen


def main():
    kat = '--kat' in sys.argv
    src = arg('--serp')
    name = arg('--name', 'KATALOGI' if kat else src.split('-')[0])
    stop = O.load_stop(os.path.join(D, '..', 'stop_domeny.txt'))
    post = O.load_post(os.path.join(D, '..', 'minus_slova.txt'))
    cands = {}
    if kat:
        for l in open(os.path.join(A.OUT, 'KATALOGI.jsonl'), encoding='utf-8'):
            j = json.loads(l)
            d = j.get('domain')
            if not d or O.stop_type(d, stop):
                continue
            c = cands.setdefault(d, {'segments': set(SEGS), 'sources': set(), 'rubrics': set(), 'titles': []})
            c['sources'].add(j['source'])
            c['rubrics'].add(j.get('rubric') or '')
    else:
        def rows():
            for line in open(os.path.join(A.OUT, src), encoding='utf-8'):
                j = json.loads(line)
                for dd in j.get('docs') or []:
                    yield {'engine': j['engine'], 'query': j['query'], 'segment': j['segment'],
                           'subsegment': j['subsegment'], 'region': j['region'], 'qid': j['qid'], **dd}
        agg, _, _ = O.aggregate(rows(), stop, post)
        for d, c in agg.items():
            cands[d] = {'segments': c['segments'], 'sources': c['engines'], 'rubrics': c['regions'],
                        'titles': c['titles'], 'queries': c['queries']}
    # что уже находили раньше
    before = serp_domains('BAZA-PILOT-SERP.jsonl') | serp_domains('IDEI-SERP.jsonl')
    for other in ('GLUBINA-SERP.jsonl', 'MASSA-SERP.jsonl'):
        if other != src:
            before |= serp_domains(other)
    if not kat and os.path.exists(os.path.join(A.OUT, 'KATALOGI.jsonl')):
        before |= {json.loads(l).get('domain') for l in open(os.path.join(A.OUT, 'KATALOGI.jsonl'), encoding='utf-8')}
    sayty = {}
    for p in (A.SAYTY, os.path.join(A.OUT, 'idei-sayty.jsonl'), CACHE):
        if os.path.exists(p):
            for l in open(p, encoding='utf-8'):
                j = json.loads(l)
                sayty[j['domain']] = j
    todo = [{'domain': d} for d in cands if d not in sayty]
    t0 = time.time()
    with open(CACHE, 'a', encoding='utf-8') as f, ThreadPoolExecutor(16) as ex:
        for rec in ex.map(A.proverit, todo):
            sayty[rec['domain']] = rec
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    et = json.load(open(A.ETALON, encoding='utf-8'))
    kd, ki = set(et['domains']), set(et['inns'])
    out, cnt = [], Counter()
    by_seg = defaultdict(Counter)
    for d, c in cands.items():
        s = sayty.get(d, {})
        alive = bool(s.get('http_status')) and s['http_status'] < 400
        sc = s.get('scores') or {}
        segs = [x for x in c['segments'] if x in sc]
        best_seg = max(segs, key=lambda x: sc[x]) if segs else ''
        best = sc.get(best_seg) if best_seg else None
        title = s.get('title') or (c['titles'][0] if c['titles'] else '')
        tip = O.tip_sayta(title, d) if alive else ''
        prof = alive and not s.get('is_parked') and best is not None and best >= O.POROG and not tip
        ids = (s.get('inn') or []) + (s.get('unp') or [])
        st = O.status(d if d in kd else (s.get('final_domain') or d), ids, kd, ki) if prof else ''
        novel = d not in before
        cnt['kandidatov'] += 1
        cnt['zhivyh'] += alive
        cnt['profilnyh'] += prof
        cnt['novyh_dlya_bazy'] += prof and st.startswith('new')
        cnt['novyh_i_ranee_ne_nahodili'] += prof and st.startswith('new') and novel
        if prof:
            by_seg[best_seg]['prof'] += 1
            by_seg[best_seg]['new'] += st.startswith('new')
            by_seg[best_seg]['novel'] += st.startswith('new') and novel
        out.append({'domain': O.domain_unicode(d), 'segment': best_seg, 'profile_score': best, 'tip': tip,
                    'status': st, 'ranee_ne_nahodili': int(novel), 'sources': '|'.join(sorted(c['sources'])),
                    'rubrics': '|'.join(sorted(c['rubrics']))[:200], 'inn': '|'.join(s.get('inn') or []),
                    'unp': '|'.join(s.get('unp') or []), 'title': title})
    out.sort(key=lambda r: (r['status'] == '', not r['ranee_ne_nahodili'], r['segment']))
    with open(os.path.join(A.DROP, f'NOVYE-{name}.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    src_cnt = Counter()
    if kat:
        for d, c in cands.items():
            r = next(x for x in out if x['domain'] == O.domain_unicode(d))
            for s_ in c['sources']:
                src_cnt[s_ + ':vsego'] += 1
                src_cnt[s_ + ':novye'] += bool(r['status'].startswith('new'))
    print('===ИТОГ===')
    print(json.dumps({'name': name, **cnt, 'dokachano_saytov': len(todo), 'sek': round(time.time() - t0),
                      'po_segmentam': {k: dict(v) for k, v in by_seg.items()}, 'po_istochnikam': dict(src_cnt)},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
