#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка гипотезы «мы собираем всю выдачу».

Стратегия работает, только если по спорному запросу оба сайта РЕАЛЬНО стоят
в топе одновременно. Проверяем по данным:
  1. CTR на спорных запросах против уникальных;
  2. сколько спорных запросов имеют 2+ сайта в топ-10 (и сколько — только один);
  3. как делятся показы между первым и вторым сайтом по одному запросу
     (если второй получает единицы процентов — его в выдаче нет, а не «собрали»);
  4. что реально добавляет второй сайт в кликах.
Разрезы отдельно по Яндексу и Google: механика разная.
"""
import sys, os, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_overlap as bo

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
rows_q = bo.load_q_files(SRC)


def block(engine, label):
    agg = bo.aggregate(rows_q, engine)
    owners = collections.defaultdict(list)
    for (d, q), v in agg.items():
        owners[q].append((d, v))

    print(f"\n{'='*100}\n### {label}\n{'='*100}")

    # --- 1. CTR: спорные против уникальных ---
    for name, cond in (("запрос только у одного сайта", lambda l: len(l) == 1),
                       ("запрос у 2+ сайтов", lambda l: len(l) > 1)):
        imp = clk = 0
        for q, lst in owners.items():
            if not cond(lst):
                continue
            for d, v in lst:
                imp += v[0]; clk += v[1]
        print(f"{name:<32} показов {imp:>9,}  кликов {clk:>7,}  CTR {clk/max(imp,1)*100:>5.2f}%")

    # --- 2. реально ли оба в топ-10 ---
    cont = {q: l for q, l in owners.items() if len(l) > 1}
    # берём только запросы с осмысленным объёмом
    cont = {q: l for q, l in cont.items() if sum(v[0] for _, v in l) >= 50}
    both_top10 = one_top10 = none_top10 = 0
    imp_both = imp_one = imp_none = 0
    clk_both = clk_one = clk_none = 0
    for q, lst in cont.items():
        n10 = sum(1 for _, v in lst if 0 < v[2] <= 10)
        i = sum(v[0] for _, v in lst); c = sum(v[1] for _, v in lst)
        if n10 >= 2:
            both_top10 += 1; imp_both += i; clk_both += c
        elif n10 == 1:
            one_top10 += 1; imp_one += i; clk_one += c
        else:
            none_top10 += 1; imp_none += i; clk_none += c
    tot = len(cont) or 1
    print(f"\nспорных запросов с объёмом >= 50 показов: {tot:,}")
    for name, n, i, c in (("2+ моих сайта в топ-10 (выдача реально собрана)", both_top10, imp_both, clk_both),
                          ("в топ-10 только один, остальные ниже", one_top10, imp_one, clk_one),
                          ("ни одного в топ-10", none_top10, imp_none, clk_none)):
        print(f"  {name:<48} {n:>6,} ({n/tot*100:>4.1f}%)  показов {i:>9,}  кликов {c:>6,}  CTR {c/max(i,1)*100:>5.2f}%")

    # --- 3. как делятся показы между лидером и вторым ---
    ratios = []
    for q, lst in cont.items():
        s = sorted((v[0] for _, v in lst), reverse=True)
        if len(s) >= 2 and s[0] > 0:
            ratios.append(s[1] / s[0])
    if ratios:
        ratios.sort()
        print(f"\nдоля показов второго сайта от первого по одному запросу:")
        print(f"  медиана {statistics.median(ratios)*100:>5.1f}%   "
              f"25-й перцентиль {ratios[len(ratios)//4]*100:>5.1f}%   "
              f"75-й {ratios[len(ratios)*3//4]*100:>5.1f}%")
        for thr in (0.05, 0.10, 0.25, 0.50):
            n = sum(1 for r in ratios if r < thr)
            print(f"  второй получает < {thr*100:>2.0f}% показов первого: {n:>6,} запросов ({n/len(ratios)*100:.1f}%)")

    # --- 4. что добавляет второй сайт в кликах ---
    add_clk = lead_clk = 0
    for q, lst in cont.items():
        s = sorted(lst, key=lambda x: -x[1][0])
        lead_clk += s[0][1][1]
        add_clk += sum(v[1] for _, v in s[1:])
    print(f"\nна спорных запросах: клики лидера {lead_clk:,}, "
          f"клики всех остальных своих сайтов {add_clk:,} "
          f"(+{add_clk/max(lead_clk,1)*100:.1f}% к лидеру)")


block("Яндекс", "ЯНДЕКС")
block("Google", "GOOGLE")
