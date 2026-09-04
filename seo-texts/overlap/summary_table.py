#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сводная таблица по сайтам: сколько трафика уникально, сколько делится с соседями."""
import sys, os, csv, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_overlap as bo

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
MIN = 10

rows_q = bo.load_q_files(SRC)
agg = bo.aggregate(rows_q)
idx = bo.site_index(agg)
sites = sorted(idx, key=lambda s: -sum(v[0] for v in idx[s].values()))

owners = collections.defaultdict(list)
for (d, q), v in agg.items():
    owners[q].append((d, v))

tot_i = sum(v[0] for v in agg.values())
tot_c = sum(v[1] for v in agg.values())
sh_i = sum(v[0] for (d, q), v in agg.items() if len(owners[q]) > 1)
sh_c = sum(v[1] for (d, q), v in agg.items() if len(owners[q]) > 1)
print(f"всего показов {tot_i:,}, кликов {tot_c:,}")
print(f"на спорных запросах (2+ сайта): показов {sh_i:,} ({sh_i/tot_i*100:.1f}%), "
      f"кликов {sh_c:,} ({sh_c/tot_c*100:.1f}%)")

out = []
for s in sites:
    qs = idx[s]
    imp = sum(v[0] for v in qs.values()) or 1
    clk = sum(v[1] for v in qs.values())
    uniq_i = sum(v[0] for q, v in qs.items() if len(owners[q]) == 1)
    uniq_c = sum(v[1] for q, v in qs.items() if len(owners[q]) == 1)
    second_i = second_q = 0
    partner = collections.Counter()
    for q, v in qs.items():
        lst = owners[q]
        if len(lst) < 2:
            continue
        best = min(lst, key=lambda x: x[1][2] if x[1][2] > 0 else 999)
        for d2, _ in lst:
            if d2 != s:
                partner[d2] += v[0]
        if best[0] != s and v[0] >= MIN:
            second_i += v[0]
            second_q += 1
    top = partner.most_common(1)
    out.append([s, len(qs), imp, clk, f"{uniq_i/imp*100:.1f}", f"{uniq_c/max(clk,1)*100:.1f}",
                f"{second_i/imp*100:.1f}", second_q,
                top[0][0] if top else "", f"{top[0][1]/imp*100:.1f}" if top else ""])

hdr = ["сайт", "запросов", "показов", "кликов", "уникальные показы %", "уникальные клики %",
       "показы вторым номером %", "запросов вторым номером", "главный сосед", "показов пересечено с ним %"]
with open(os.path.join(OUT, "svodka-po-saytam.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";"); w.writerow(hdr); w.writerows(out)

print(f"\n{'сайт':<30}{'показов':>9}{'уник.показы':>13}{'уник.клики':>12}{'вторым №':>10}  главный сосед")
for r in out:
    print(f"{r[0]:<30}{r[2]:>9,}{r[4]+'%':>13}{r[5]+'%':>12}{r[6]+'%':>10}  {r[8]} ({r[9]}%)")
