#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Почему ВЧ-запросы не в топе: диагностика на уровне страниц.

Два дефекта, которые видно по данным:
  1. по запросу ранжируется не та страница, в которую целится план ссылок;
  2. за один интент бьётся несколько своих страниц.
Источники: pagequeries.csv (запрос → страница, Яндекс), plan_queries.csv
(целевые страницы плана), q_*.txt (показы по запросам).
"""
import sys, os, csv, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_overlap as bo

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
MIN_IMP = 100

pq = collections.defaultdict(list)
with open(os.path.join(SRC, "pagequeries.csv"), encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh, delimiter=";"):
        try:
            im, pos = int(r["ya_im"]), float(r["ya_pos"] or 0)
        except ValueError:
            continue
        if im and pos:
            pq[bo.norm(r["query"])].append((r["dom"], r["path"], im, pos))

target = {}            # (сайт, запрос) -> страница, в которую целится план
with open(os.path.join(SRC, "plan_queries.csv"), encoding="utf-8-sig") as fh:
    for r in csv.DictReader(fh, delimiter=";"):
        target[(r["сайт"], bo.norm(r["запрос"]))] = r["страница"]

rows = [r for r in bo.load_q_files(SRC) if r[1] == "Яндекс"]
qim = collections.Counter()
for d, e, q, c, i, p in rows:
    qim[q] += i

mismatch, split = [], []
for q, pages in pq.items():
    if qim[q] < MIN_IMP:
        continue
    by_site = collections.defaultdict(list)
    for d, p, im, pos in pages:
        by_site[d].append((im, pos, p))
    for d, lst in by_site.items():
        lst.sort(reverse=True)
        shown = lst[0][2]                       # страница, которую реально показывает Яндекс
        tgt = target.get((d, q))
        if tgt and tgt != shown:
            mismatch.append([q, qim[q], d, tgt, shown, round(lst[0][1], 1), lst[0][0]])
        if len(lst) > 1:
            split.append([q, qim[q], d, len(lst),
                          " | ".join(f"{p} поз{pos:.0f}" for im, pos, p in
                                     sorted(lst, key=lambda x: x[1])[:5])])

mismatch.sort(key=lambda r: -r[1])
split.sort(key=lambda r: -r[1])

with open(os.path.join(OUT, "vch-ne-ta-stranica.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["запрос", "показов Яндекса", "сайт", "целевая страница плана",
                "страница, которую показывает Яндекс", "её позиция", "её показы"])
    w.writerows(mismatch)

with open(os.path.join(OUT, "vch-neskolko-stranic.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["запрос", "показов Яндекса", "сайт", "своих страниц", "страницы (позиция)"])
    w.writerows(split)

print(f"запросов Яндекса с >= {MIN_IMP} показов: "
      f"{sum(1 for q in pq if qim[q] >= MIN_IMP):,}")
print(f"расхождений «план целится не туда, что ранжируется»: {len(mismatch)}")
print(f"запросов, где у одного сайта конкурируют 2+ страницы: {len(split)}")
print(f"\n{'запрос':<36}{'показы':>7}  сайт → план / что показывает Яндекс")
for q, im, d, tgt, shown, pos, pim in mismatch[:12]:
    print(f"{q[:35]:<36}{im:>7,}  {d}")
    print(f"{'':<43}план:   {tgt}")
    print(f"{'':<43}Яндекс: {shown}  (поз {pos})")
print(f"\nCSV: vch-ne-ta-stranica.csv, vch-neskolko-stranic.csv")
