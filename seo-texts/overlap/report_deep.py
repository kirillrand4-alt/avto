#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Углублённый разрез: значимые пересечения (без хвоста), кластеры сайтов,
двойное присутствие в одной выдаче и «кто у кого забирает»."""
import sys, os, csv, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_overlap as bo

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
MIN = 10          # порог показов с каждой стороны — отсекаем случайный хвост


def main():
    rows_q = bo.load_q_files(SRC)

    for engine, label in ((None, "ВСЕ (Google+Яндекс)"), ("Яндекс", "только Яндекс"), ("Google", "только Google")):
        agg = bo.aggregate(rows_q, engine)
        idx = bo.site_index(agg)
        sites = sorted(idx, key=lambda s: -sum(v[0] for v in idx[s].values()))

        # --- значимое пересечение: обе стороны имеют >= MIN показов по запросу ---
        big = {s: {q for q, v in idx[s].items() if v[0] >= MIN} for s in sites}
        print(f"\n{'='*104}\n### {label}: ЗНАЧИМЫЕ ПЕРЕСЕЧЕНИЯ (у обоих сайтов >= {MIN} показов по запросу)\n{'='*104}")
        print(f"{'сайт A':<25} {'сайт B':<25} {'общих':>7} {'перекр.':>8} "
              f"{'двойн. показы':>14} {'доля A':>8} {'доля B':>8} {'кликов A':>9} {'кликов B':>9}")
        pairs = []
        for i, a in enumerate(sites):
            for b in sites[i + 1:]:
                inter = big[a] & big[b]
                if len(inter) < 3:
                    continue
                ia = sum(idx[a][q][0] for q in inter)
                ib = sum(idx[b][q][0] for q in inter)
                ca = sum(idx[a][q][1] for q in inter)
                cb = sum(idx[b][q][1] for q in inter)
                ta = sum(v[0] for v in idx[a].values()) or 1
                tb = sum(v[0] for v in idx[b].values()) or 1
                pairs.append((len(inter), a, b, ia + ib, ia / ta, ib / tb, ca, cb,
                              len(inter) / min(len(big[a]), len(big[b]))))
        for n, a, b, dbl, sa, sb, ca, cb, ov in sorted(pairs, key=lambda x: -x[3])[:30]:
            print(f"{a:<25} {b:<25} {n:>7,} {ov*100:>7.1f}% {dbl:>14,} "
                  f"{sa*100:>7.1f}% {sb*100:>7.1f}% {ca:>9,} {cb:>9,}")

        if engine is None:
            # --- кто у кого «на хвосте»: показы сайта на запросах, где выше стоит свой же ---
            owners = collections.defaultdict(list)
            for (d, q), v in agg.items():
                owners[q].append((d, v))
            worse = collections.Counter()
            worse_q = collections.Counter()
            taker = collections.Counter()
            for q, lst in owners.items():
                if len(lst) < 2:
                    continue
                best = min(lst, key=lambda x: x[1][2] if x[1][2] > 0 else 999)
                for d, v in lst:
                    if d != best[0] and v[0] >= MIN:
                        worse[d] += v[0]
                        worse_q[d] += 1
                        taker[(d, best[0])] += v[0]
            print(f"\n{'='*104}\n### ПОКАЗЫ «ВТОРЫМ НОМЕРОМ»: сайт показан по запросу, где его же соседний сайт стоит выше\n{'='*104}")
            print(f"{'сайт':<30} {'запросов':>10} {'показов вторым':>16} {'доля показов сайта':>20}  главный перехватчик")
            for s in sites:
                tot = sum(v[0] for v in idx[s].values()) or 1
                if not worse[s]:
                    continue
                top = max(((k[1], v) for k, v in taker.items() if k[0] == s), key=lambda x: x[1], default=("", 0))
                print(f"{s:<30} {worse_q[s]:>10,} {worse[s]:>16,} {worse[s]/tot*100:>19.1f}%  {top[0]} ({top[1]:,})")

    # --- кластеры по коэффициенту перекрытия (порог 25%) ---
    agg = bo.aggregate(rows_q)
    idx = bo.site_index(agg)
    sites = sorted(idx, key=lambda s: -sum(v[0] for v in idx[s].values()))
    sets = {s: set(idx[s]) for s in sites}
    parent = {s: s for s in sites}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    links = []
    for i, a in enumerate(sites):
        for b in sites[i + 1:]:
            inter = len(sets[a] & sets[b])
            if not inter:
                continue
            ov = inter / min(len(sets[a]), len(sets[b]))
            if ov >= 0.25:
                links.append((ov, a, b))
                parent[find(a)] = find(b)
    groups = collections.defaultdict(list)
    for s in sites:
        groups[find(s)].append(s)
    print(f"\n{'='*104}\n### КЛАСТЕРЫ (связь, если общих запросов >= 25% от меньшего сайта)\n{'='*104}")
    for g in sorted(groups.values(), key=lambda g: -sum(sum(v[0] for v in idx[s].values()) for s in g)):
        imp = sum(sum(v[0] for v in idx[s].values()) for s in g)
        mark = "СВЯЗАННЫЕ" if len(g) > 1 else "отдельно"
        print(f"[{mark}] показов {imp:>9,}: " + ", ".join(sorted(g, key=lambda s: -sum(v[0] for v in idx[s].values()))))


if __name__ == "__main__":
    main()
