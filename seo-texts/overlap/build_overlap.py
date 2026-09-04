#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пересечение сайтов владельца по поисковым запросам.

Источник: выгрузка запросов по 27 доменам с дропа (q_<домен>.txt,
Google + Яндекс, период 2026-05-25 — 2026-08-24) и yq.csv (только Яндекс,
2026-06-18 — 2026-08-17) — как перекрёстная проверка.

Считаем:
  * профиль каждого сайта (запросы / показы / клики);
  * попарное пересечение: общие запросы, Жаккар, коэффициент перекрытия,
    доля показов сайта, приходящаяся на общие с соседом запросы;
  * сколько всего запросов делят 2+ сайта и сколько на них показов;
  * список самых дорогих спорных запросов с позициями обоих сайтов.
"""
import csv, glob, os, re, sys, json, collections

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."

WS = re.compile(r"\s+")


def num(x, nd=1):
    """Число для CSV: десятичная запятая. С точкой русский Excel читает
    17.6 как дату 17 июня и портит колонку позиций."""
    return f"{x:.{nd}f}".replace(".", ",")


def norm(q):
    return WS.sub(" ", q.strip().lower().replace("ё", "е"))


def load_q_files(src):
    """q_<домен>.txt -> (домен, поисковик, запрос) -> [клики, показы, позиция]."""
    rows = []
    for path in sorted(glob.glob(os.path.join(src, "q_*.txt"))):
        with open(path, encoding="utf-8-sig") as fh:
            lines = fh.read().splitlines()
        domain = lines[0].split(";", 1)[1].strip()
        try:
            start = lines.index("поисковик;запрос;клики;показы;средняя позиция") + 1
        except ValueError:
            raise SystemExit("нет шапки таблицы в " + path)
        for line in lines[start:]:
            if not line.strip():
                continue
            parts = line.split(";")
            if len(parts) < 5:
                continue
            engine, query, clicks, imps, pos = parts[0], ";".join(parts[1:-3]), parts[-3], parts[-2], parts[-1]
            rows.append((domain, engine, norm(query), int(clicks), int(imps), float(pos or 0)))
    return rows


def load_yq(src):
    path = os.path.join(src, "yq.csv")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        rd = csv.DictReader(fh, delimiter=";")
        for r in rd:
            rows.append((r["site"], "Яндекс", norm(r["query"]),
                         int(r["clicks"]), int(r["impressions"]), float(r["position"] or 0)))
    return rows


def aggregate(rows, engine=None):
    """(домен, запрос) -> показы, клики, позиция (взвешенная по показам)."""
    imp = collections.defaultdict(int)
    clk = collections.defaultdict(int)
    posw = collections.defaultdict(float)
    for domain, eng, q, c, i, p in rows:
        if engine and eng != engine:
            continue
        if not q:
            continue
        imp[(domain, q)] += i
        clk[(domain, q)] += c
        posw[(domain, q)] += p * max(i, 1)
    out = {}
    for k, i in imp.items():
        out[k] = (i, clk[k], posw[k] / max(i, 1))
    return out


def site_index(agg):
    idx = collections.defaultdict(dict)          # домен -> запрос -> (показы, клики, позиция)
    for (domain, q), v in agg.items():
        idx[domain][q] = v
    return idx


def pair_stats(idx, min_imp=0):
    sites = sorted(idx, key=lambda s: -sum(v[0] for v in idx[s].values()))
    sets = {}
    for s in sites:
        sets[s] = {q for q, v in idx[s].items() if v[0] >= min_imp}
    res = []
    for a_i, a in enumerate(sites):
        for b in sites[a_i + 1:]:
            inter = sets[a] & sets[b]
            if not inter:
                continue
            union = len(sets[a] | sets[b])
            imp_a_tot = sum(idx[a][q][0] for q in sets[a]) or 1
            imp_b_tot = sum(idx[b][q][0] for q in sets[b]) or 1
            imp_a_sh = sum(idx[a][q][0] for q in inter)
            imp_b_sh = sum(idx[b][q][0] for q in inter)
            res.append({
                "a": a, "b": b,
                "n_a": len(sets[a]), "n_b": len(sets[b]),
                "shared": len(inter),
                "jaccard": len(inter) / union,
                "overlap": len(inter) / min(len(sets[a]), len(sets[b])),
                "imp_share_a": imp_a_sh / imp_a_tot,
                "imp_share_b": imp_b_sh / imp_b_tot,
                "imp_shared": imp_a_sh + imp_b_sh,
            })
    return sites, sets, res


def main():
    rows_q = load_q_files(SRC)
    rows_y = load_yq(SRC)
    print(f"строк q_*.txt: {len(rows_q):,}; строк yq.csv: {len(rows_y):,}")

    datasets = {
        "ВСЕ (Google+Яндекс)": aggregate(rows_q),
        "только Яндекс": aggregate(rows_q, "Яндекс"),
        "только Google": aggregate(rows_q, "Google"),
    }

    report = {}
    for label, agg in datasets.items():
        idx = site_index(agg)
        sites, sets, pairs = pair_stats(idx)
        # сколько сайтов делят один запрос
        owners = collections.defaultdict(set)
        qimp = collections.defaultdict(int)
        for (d, q), v in agg.items():
            owners[q].add(d)
            qimp[q] += v[0]
        dist = collections.Counter(len(v) for v in owners.values())
        imp_by_n = collections.Counter()
        for q, o in owners.items():
            imp_by_n[len(o)] += qimp[q]
        report[label] = {
            "sites": sites, "idx": idx, "pairs": pairs,
            "owners": owners, "qimp": qimp, "dist": dist, "imp_by_n": imp_by_n,
            "agg": agg,
        }
    return report, rows_q, rows_y


if __name__ == "__main__":
    main()
