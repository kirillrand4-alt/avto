#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Топ-15 запросов каждого сайта: средняя позиция по ним и пересечение с другими сайтами."""
import sys, os, csv, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_overlap as bo

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."
N = 15

rows = bo.load_q_files(SRC)
agg_all = bo.aggregate(rows)                 # показы, клики, позиция (взвеш.) по обоим ПС
agg_ya = bo.aggregate(rows, "Яндекс")
agg_go = bo.aggregate(rows, "Google")
idx = bo.site_index(agg_all)
sites = sorted(idx, key=lambda s: -sum(v[0] for v in idx[s].values()))

top = {s: [q for q, _ in sorted(idx[s].items(), key=lambda kv: -kv[1][0])[:N]] for s in sites}
topset = {s: set(v) for s, v in top.items()}
allset = {s: set(idx[s]) for s in sites}


def wpos(site, qs, agg):
    i = sum(agg[(site, q)][0] for q in qs if (site, q) in agg)
    if not i:
        return None
    return sum(agg[(site, q)][2] * agg[(site, q)][0] for q in qs if (site, q) in agg) / i


print(f"### СРЕДНЯЯ ПОЗИЦИЯ ПО ТОП-{N} ЗАПРОСАМ САЙТА (взвешено по показам)\n")
print(f"{'сайт':<30}{'показы топ-15':>14}{'доля сайта':>11}{'кликов':>8}"
      f"{'поз Яндекс':>12}{'поз Google':>12}{'из 15 есть у других':>21}{'сайтов-соседей':>16}")
table = []
for s in sites:
    qs = top[s]
    i = sum(idx[s][q][0] for q in qs)
    c = sum(idx[s][q][1] for q in qs)
    tot = sum(v[0] for v in idx[s].values()) or 1
    py, pg = wpos(s, qs, agg_ya), wpos(s, qs, agg_go)
    nb = {o for o in sites if o != s and topset[s] & allset[o]}
    shared = sum(1 for q in qs if any((o, q) in agg_all for o in sites if o != s))
    table.append([s, i, f"{i/tot*100:.1f}", c,
                  f"{py:.1f}" if py else "", f"{pg:.1f}" if pg else "", shared, len(nb)])
    print(f"{s:<30}{i:>14,}{i/tot*100:>10.1f}%{c:>8,}"
          f"{(f'{py:.1f}' if py else '—'):>12}{(f'{pg:.1f}' if pg else '—'):>12}"
          f"{shared:>21}{len(nb):>16}")

with open(os.path.join(OUT, "top15-pozicii.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["сайт", "показов в топ-15", "доля показов сайта %", "кликов в топ-15",
                "ср. позиция Яндекс", "ср. позиция Google", "запросов из 15 есть у других сайтов",
                "сколько сайтов пересекаются"])
    w.writerows(table)

# --- матрица: сколько из топ-15 сайта-строки есть у сайта-столбца ---
print(f"\n\n### ПЕРЕСЕЧЕНИЕ ТОП-{N}: сколько из {N} запросов строки встречается у столбца")
print("    (в скобках — сколько из них входит и в топ-15 столбца)\n")
hdr = [s.replace("-kompressor", "-k").replace("-compressor", "-c")
        .replace(".prokompressor.ru", ".pk").replace("prokompressor.ru", "PROKOMP")[:11] for s in sites]
print(f"{'':<30}" + "".join(f"{h:>12}" for h in hdr[:12]))
for s in sites:
    cells = []
    for o in sites[:12]:
        if o == s:
            cells.append("·")
            continue
        a = len(topset[s] & allset[o]); b = len(topset[s] & topset[o])
        cells.append(f"{a}({b})" if a else "")
    print(f"{s:<30}" + "".join(f"{c:>12}" for c in cells))

with open(os.path.join(OUT, "top15-matrica.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow([f"из топ-{N} сайта-строки встречается у сайта-столбца"] + sites)
    for s in sites:
        w.writerow([s] + ["·" if o == s else (len(topset[s] & allset[o]) or "") for o in sites])
    w.writerow([])
    w.writerow([f"из них входит и в топ-{N} столбца"] + sites)
    for s in sites:
        w.writerow([s] + ["·" if o == s else (len(topset[s] & topset[o]) or "") for o in sites])

# --- построчная расшифровка топ-15 ---
with open(os.path.join(OUT, "top15-zaprosy.csv"), "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow(["сайт", "№", "запрос", "показы", "клики", "позиция Яндекс", "позиция Google",
                "другие мои сайты по этому запросу (позиция)"])
    for s in sites:
        for k, q in enumerate(top[s], 1):
            others = [f"{o} {agg_all[(o,q)][2]:.0f}" for o in sites
                      if o != s and (o, q) in agg_all]
            py = agg_ya.get((s, q)); pg = agg_go.get((s, q))
            w.writerow([s, k, q, idx[s][q][0], idx[s][q][1],
                        f"{py[2]:.1f}" if py else "", f"{pg[2]:.1f}" if pg else "",
                        ", ".join(others)])
print("\nCSV: top15-pozicii.csv, top15-matrica.csv, top15-zaprosy.csv")
