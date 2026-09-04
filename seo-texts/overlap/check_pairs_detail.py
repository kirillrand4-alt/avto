#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, collections
sys.path.insert(0, "/home/user/avto/seo-texts/overlap")
import build_overlap as bo
rows = bo.load_q_files(".")

# 1. распределение позиций и CTR по корзинам позиций, отдельно по поисковикам
print("=== ПОЗИЦИИ И CTR ПО КОРЗИНАМ ===")
for eng in ("Яндекс", "Google"):
    buckets = collections.defaultdict(lambda: [0, 0])
    for d, e, q, c, i, p in rows:
        if e != eng or i == 0:
            continue
        b = "1-3" if p <= 3 else "4-10" if p <= 10 else "11-20" if p <= 20 else "21-50" if p <= 50 else "50+"
        buckets[b][0] += i; buckets[b][1] += c
    tot = sum(v[0] for v in buckets.values())
    print(f"\n{eng}: показов {tot:,}")
    for b in ("1-3", "4-10", "11-20", "21-50", "50+"):
        i, c = buckets[b]
        print(f"  поз {b:<6} показов {i:>9,} ({i/tot*100:>4.1f}%)  кликов {c:>7,}  CTR {c/max(i,1)*100:>6.2f}%")

# 2. пара berg в Яндексе: одновременность присутствия
print("\n=== BERG-ПАРА В ЯНДЕКСЕ: ТОП-25 ОБЩИХ ЗАПРОСОВ ===")
agg = bo.aggregate(rows, "Яндекс")
A, B = "berg-compressor.com", "berg-kompressor.ru"
shared = [(agg[(A, q)][0] + agg[(B, q)][0], q) for (d, q) in agg if d == A and (B, q) in agg]
shared.sort(reverse=True)
print(f"общих запросов в Яндексе: {len(shared)}")
print(f"{'запрос':<42}{'berg-c показы/клики/поз':>26}{'berg-k показы/клики/поз':>26}")
for tot, q in shared[:25]:
    a, b = agg[(A, q)], agg[(B, q)]
    print(f"{q[:41]:<42}{f'{a[0]}/{a[1]}/{a[2]:.0f}':>26}{f'{b[0]}/{b[1]}/{b[2]:.0f}':>26}")

# 3. что теряем при схлопывании: уникальные клики каждого сайта-спутника
print("\n=== УНИКАЛЬНЫЙ ВКЛАД САЙТА (клики по запросам, которых нет у других моих) ===")
agg_all = bo.aggregate(rows)
owners = collections.defaultdict(set)
for (d, q) in agg_all:
    owners[q].add(d)
idx = bo.site_index(agg_all)
out = []
for s, qs in idx.items():
    uc = sum(v[1] for q, v in qs.items() if len(owners[q]) == 1)
    tc = sum(v[1] for v in qs.values())
    out.append((tc, uc, s))
out.sort(reverse=True)
print(f"{'сайт':<32}{'кликов всего':>13}{'уникальных':>12}{'доля':>7}")
for tc, uc, s in out:
    print(f"{s:<32}{tc:>13,}{uc:>12,}{uc/max(tc,1)*100:>6.0f}%")
