#!/usr/bin/env python3
"""Принципы отбора доноров 1 и 4 (16.11.2026), поверх donory-google.json.

1. Эффект донора: у каждого конкурента, получившего ссылку с донора (Ahrefs first_seen),
   трафик в Google (Semrush) за +3..+8 мес. к -6..-1 мес., минус медиана рынка за то же
   окно. По донору: число случаев и медиана. Мало случаев = шум, только отсев явных «не помогает».
4. Признаки фермы: исходящие dofollow-домены донора (Ahrefs, поле 11) и их отношение
   к входящим (поле 10); доля конкурентов со ссылкой с донора; обвалы трафика донора
   (3 мес. к 3 предыдущим < 0.4 за последние 3 года).
Выход: donory-principy.json + таблица.
"""
import json
import math
import os
import statistics as st
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
SM = 20


def ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[4:]) - 1 + k
    return f'{y + m // 12}{m % 12 + 1:02d}'


def growth(ser, ym):
    pre = [ser.get(ym_add(ym, -k)) for k in range(1, 7)]
    post = [ser.get(ym_add(ym, k)) for k in range(3, 9)]
    if None in pre or None in post:
        return None
    return math.log((st.mean(post) + SM) / (st.mean(pre) + SM))


def load_trend(name):
    T = {}
    for l in open(os.path.join(DIR, name), encoding='utf-8'):
        d = json.loads(l)
        if not d.get('error'):
            T[d['domain']] = {m[0][:6]: (m[1] or 0) for m in d['m']}
    return T


def main():
    TK = load_trend('konkurenty-trend.jsonl')
    TD = load_trend('donory-trend.jsonl')
    G = json.load(open(os.path.join(DIR, 'donory-google.json'), encoding='utf-8'))['all']
    cand = {d['domain'] for d in G}
    links = defaultdict(list)       # донор -> [(конкурент, ym)]
    meta = {}
    targets = set()
    for l in open(os.path.join(DIR, 'konkurenty-refdomains.jsonl'), encoding='utf-8'):
        d = json.loads(l)
        targets.add(d['target'])
        for r in d['rows']:
            if r[1] in cand and r[7]:
                links[r[1]].append((d['target'], r[7][:7].replace('-', '')))
                meta[r[1]] = (int(float(r[10] or 0)), int(float(r[11] or 0)))
    months = sorted({ym for s in TK.values() for ym in s})
    market = {}
    for ym in months:
        gs = [g for g in (growth(s, ym) for s in TK.values()) if g is not None]
        if gs:
            market[ym] = st.median(gs)
    res = []
    for d in G:
        dom = d['domain']
        effs = []
        for tgt, ym in links.get(dom, []):
            s = TK.get(tgt)
            if not s or max(s.values()) < 50 or ym not in market:
                continue
            g = growth(s, ym)
            if g is not None:
                effs.append(g - market[ym])
        inn, out = meta.get(dom, (0, 0))
        ser = [v for k, v in sorted(TD.get(dom, {}).items())][-39:]
        crash = 0
        for i in range(6, len(ser) + 1):
            a, b = st.mean(ser[i - 6:i - 3]), st.mean(ser[i - 3:i])
            if a >= 100 and (b + SM) / (a + SM) < 0.4:
                crash = 1
        res.append({**{k: d.get(k) for k in ('domain', 'tema', 'tip', 'n', 'g_tr', 'g_dyn', 'mira')},
                    'eff_n': len(effs),
                    'eff_x': round(math.exp(st.median(effs)), 2) if effs else None,
                    'eff_up': round(sum(e > math.log(1.2) for e in effs) / len(effs), 2) if effs else None,
                    'in_do': inn, 'out_do': out, 'out_in': round(out / max(inn, 1), 1),
                    'konk_share': round(d['n'] / len(targets), 2), 'crash': crash})
    json.dump(res, open(os.path.join(DIR, 'donory-principy.json'), 'w'), ensure_ascii=False, indent=1)
    sel = [r for r in res if r['tema'] in ('наша', 'смежная')]
    sel.sort(key=lambda r: -(r['g_tr'] or 0))
    print(f"{'домен':24} {'тема':7} конк G-тр  дин  | эфф n  x    up  | вх   исх    исх/вх доля обвал цена")
    for r in sel:
        print(f"{r['domain']:24} {r['tema'][:7]:7} {r['n']:3} {r['g_tr']:6} {r['g_dyn']:<4} | {r['eff_n']:3} "
              f"{str(r['eff_x']):5} {str(r['eff_up']):5}| {r['in_do']:5} {r['out_do']:7} {r['out_in']:6} "
              f"{r['konk_share']:.2f} {r['crash']} {r['mira'] or '-'}")


if __name__ == '__main__':
    main()
