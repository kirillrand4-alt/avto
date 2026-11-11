#!/usr/bin/env python3
"""Помогли ли конкурентам ссылки: всплески новых ссылающихся доменов (Ahrefs first_seen)
против помесячной органики Google RU (Semrush, konkurenty-trend.jsonl).

Метод: событие = квартал, когда у конкурента появилось >= MIN_EV новых dofollow-доменов
(DR>=10, не спам) и это >= 2x его обычного квартала. Рост = log(средний трафик
месяцев +3..+8 / средний трафик месяцев -6..-1), минус медиана того же окна по всем
конкурентам (поправка на рынок/апдейты). Контроль - кварталы того же домена без всплеска.
Оговорки: Ahrefs отдаёт только живые ссылки (потерянные не видны), Semrush ru = Google,
не Яндекс; трафик Semrush - модельный.
"""
import json
import math
import os
import statistics as st
from collections import defaultdict

DIR = os.path.dirname(os.path.abspath(__file__))
MIN_EV = int(os.environ.get('MIN_EV', '5'))
SMOOTH = 20


def load_trend():
    T = {}
    for l in open(os.path.join(DIR, 'konkurenty-trend.jsonl'), encoding='utf-8'):
        d = json.loads(l)
        if not d.get('error'):
            T[d['domain']] = {m[0][:6]: (m[1] or 0) for m in d['m']}
    return T


def load_links():
    media = {}
    for l in open(os.path.join(DIR, 'konkurenty-tip.jsonl'), encoding='utf-8'):
        d = json.loads(l)
        media[d['domain']] = d.get('tip', '')
    L = defaultdict(dict)
    for l in open(os.path.join(DIR, 'konkurenty-refdomains.jsonl'), encoding='utf-8'):
        d = json.loads(l)
        for r in d['rows']:
            if r[6] or not r[16] or (r[9] or 0) < 10 or not r[7]:
                continue
            L[d['target']][r[1]] = r[7][:7].replace('-', '')
    return L, media


def ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[4:]) - 1 + k
    return f'{y + m // 12}{m % 12 + 1:02d}'


def growth(ser, ym):
    pre = [ser.get(ym_add(ym, -k)) for k in range(1, 7)]
    post = [ser.get(ym_add(ym, k)) for k in range(3, 9)]
    if None in pre or None in post:
        return None
    return math.log((st.mean(post) + SMOOTH) / (st.mean(pre) + SMOOTH))


def main():
    T = load_trend()
    L, media = load_links()
    quarters = [f'{y}{m:02d}' for y in range(2019, 2026) for m in (1, 4, 7, 10)]
    quarters = [q for q in quarters if q <= '202602']
    market = {q: st.median([g for g in (growth(s, q) for s in T.values()) if g is not None] or [0])
              for q in quarters}
    ev, ctl, ev_media, rows = [], [], [], []
    for dom, links in L.items():
        ser = T.get(dom)
        if not ser or max(ser.values() or [0]) < 50:
            continue
        cnt = defaultdict(int)
        cnt_media = defaultdict(int)
        for rd, ym in links.items():
            q = ym[:4] + f'{(int(ym[4:]) - 1) // 3 * 3 + 1:02d}'
            cnt[q] += 1
            if 'СМИ' in media.get(rd, ''):
                cnt_media[q] += 1
        base = st.median([cnt.get(q, 0) for q in quarters]) or 1
        for q in quarters:
            g = growth(ser, q)
            if g is None:
                continue
            adj = g - market[q]
            if cnt.get(q, 0) >= MIN_EV and cnt[q] >= 2 * base:
                ev.append(adj)
                rows.append((dom, q, cnt[q], cnt_media.get(q, 0), round(math.exp(adj), 2)))
                if cnt_media.get(q, 0) >= 2:
                    ev_media.append(adj)
            elif cnt.get(q, 0) <= base:
                ctl.append(adj)

    def summ(name, xs):
        if not xs:
            return {'name': name, 'n': 0}
        up = sum(1 for x in xs if x > math.log(1.2)) / len(xs)
        dn = sum(1 for x in xs if x < -math.log(1.2)) / len(xs)
        return {'name': name, 'n': len(xs), 'median_x': round(math.exp(st.median(xs)), 3),
                'share_up20': round(up, 2), 'share_down20': round(dn, 2)}
    res = {'events': summ('всплеск ссылок', ev), 'media_events': summ('всплеск с >=2 СМИ', ev_media),
           'control': summ('кварталы без всплеска', ctl),
           'top_events': sorted(rows, key=lambda r: -r[4])[:15],
           'worst_events': sorted(rows, key=lambda r: r[4])[:10]}
    json.dump(res, open(os.path.join(DIR, 'konkurenty-effekt.json'), 'w'), ensure_ascii=False, indent=1)
    for k in ('events', 'media_events', 'control'):
        print(res[k])
    print('лучшие:', *res['top_events'], sep='\n ')
    print('худшие:', *res['worst_events'], sep='\n ')


if __name__ == '__main__':
    main()
