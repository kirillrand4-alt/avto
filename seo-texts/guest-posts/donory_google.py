#!/usr/bin/env python3
"""Рейтинг доноров под Google (решение владельца 16.11.2026: под Яндекс не подбираем).

Вход: konkurenty-tip.jsonl (тип/тема/конкуренты/цена Miralinks), donory-trend.jsonl
(помесячная органика Google RU из Semrush). Выход: donory-google.json + печать.
Трафик: среднее за последние 3 мес. Динамика: последние 6 мес к тем же 6 мес год назад.
"""
import json
import os
import statistics as st

DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    T = {}
    for l in open(os.path.join(DIR, 'donory-trend.jsonl'), encoding='utf-8'):
        d = json.loads(l)
        if not d.get('error'):
            T[d['domain']] = [m[1] or 0 for m in d['m']]
    out = []
    for l in open(os.path.join(DIR, 'konkurenty-tip.jsonl'), encoding='utf-8'):
        d = json.loads(l)
        s = T.get(d['domain'])
        if not s or len(s) < 19:
            continue
        g_now = st.mean(s[-3:])
        dyn = (st.mean(s[-6:]) + 10) / (st.mean(s[-18:-12]) + 10)
        d.update(g_tr=round(g_now), g_dyn=round(dyn, 2))
        out.append(d)
    ok = [d for d in out if d.get('tema') in ('наша', 'смежная') and d['g_tr'] >= 100 and d['g_dyn'] >= 0.8
          and 'доска' not in d.get('tip', '') and 'сервис' not in d.get('tip', '')]
    ok.sort(key=lambda d: (-(d['tema'] == 'наша'), -d['n'] * min(d['g_tr'], 5000)))
    json.dump({'all': out, 'shortlist': ok}, open(os.path.join(DIR, 'donory-google.json'), 'w'),
              ensure_ascii=False, indent=1)
    print(f'с данными: {len(out)}, прошли фильтр: {len(ok)}')
    for d in ok[:40]:
        print(f"{d['domain']:28} {d['tema']:8} {d.get('tip','')[:22]:22} конк {d['n']:3} G-тр {d['g_tr']:6} "
              f"дин x{d['g_dyn']:<5} mira {d.get('mira') or '-'}")


if __name__ == '__main__':
    main()
