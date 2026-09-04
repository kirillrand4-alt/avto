#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Отчёт о пересечении сайтов владельца по запросам. Печатает текст в stdout,
рядом кладёт CSV-таблицы (матрица пересечений и список спорных запросов)."""
import sys, os, csv, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_overlap as bo

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2] if len(sys.argv) > 2 else "."


def short(d):
    return d.replace("-kompressor", "-k").replace("-compressor", "-c") \
            .replace(".prokompressor.ru", ".pk").replace("prokompressor.ru", "PROKOMPRESSOR")


def main():
    report, rows_q, rows_y = bo.main()

    for label in ("ВСЕ (Google+Яндекс)", "только Яндекс", "только Google"):
        R = report[label]
        idx, dist, imp_by_n = R["idx"], R["dist"], R["imp_by_n"]
        tot_q = sum(dist.values())
        tot_i = sum(imp_by_n.values())
        print(f"\n{'='*100}\n### {label}\n{'='*100}")
        print(f"уникальных запросов по всем сайтам: {tot_q:,}   показов: {tot_i:,}")
        print("\nсколько САЙТОВ делят один и тот же запрос:")
        print(f"{'сайтов':>7} | {'запросов':>10} {'доля':>7} | {'показов':>12} {'доля':>7}")
        for n in sorted(dist):
            print(f"{n:>7} | {dist[n]:>10,} {dist[n]/tot_q*100:>6.1f}% | "
                  f"{imp_by_n[n]:>12,} {imp_by_n[n]/tot_i*100:>6.1f}%")
        shared_q = sum(v for n, v in dist.items() if n >= 2)
        shared_i = sum(v for n, v in imp_by_n.items() if n >= 2)
        print(f"ИТОГО спорных (2+ сайта): {shared_q:,} запросов ({shared_q/tot_q*100:.1f}%), "
              f"{shared_i:,} показов ({shared_i/tot_i*100:.1f}%)")

    # ---------- основной блок: ВСЕ ----------
    R = report["ВСЕ (Google+Яндекс)"]
    idx, pairs, owners, qimp, agg = R["idx"], R["pairs"], R["owners"], R["qimp"], R["agg"]
    sites = R["sites"]

    print(f"\n{'='*100}\n### ПРОФИЛЬ САЙТОВ (Google+Яндекс, 2026-05-25 — 2026-08-24)\n{'='*100}")
    print(f"{'сайт':<32} {'запросов':>10} {'показов':>10} {'кликов':>8} "
          f"{'запр. с 2+':>11} {'доля зпр':>9} {'доля показов':>13}")
    site_rows = []
    for s in sites:
        qs = idx[s]
        n = len(qs)
        imp = sum(v[0] for v in qs.values())
        clk = sum(v[1] for v in qs.values())
        sh_n = sum(1 for q in qs if len(owners[q]) > 1)
        sh_i = sum(v[0] for q, v in qs.items() if len(owners[q]) > 1)
        site_rows.append((s, n, imp, clk, sh_n, sh_n / n, sh_i / max(imp, 1)))
        print(f"{s:<32} {n:>10,} {imp:>10,} {clk:>8,} {sh_n:>11,} "
              f"{sh_n/n*100:>8.1f}% {sh_i/max(imp,1)*100:>12.1f}%")

    # ---------- попарная матрица ----------
    print(f"\n{'='*100}\n### ТОП-40 ПАР ПО ПЕРЕСЕЧЕНИЮ (сортировка по коэф. перекрытия)\n{'='*100}")
    print(f"{'сайт A':<26} {'сайт B':<26} {'общих':>7} {'перекр.':>8} {'Жаккар':>7} "
          f"{'показы A на общих':>18} {'показы B на общих':>18}")
    for p in sorted(pairs, key=lambda x: -x["overlap"])[:40]:
        print(f"{p['a']:<26} {p['b']:<26} {p['shared']:>7,} {p['overlap']*100:>7.1f}% "
              f"{p['jaccard']*100:>6.1f}% {p['imp_share_a']*100:>17.1f}% {p['imp_share_b']*100:>17.1f}%")

    print(f"\n{'='*100}\n### ТОП-30 ПАР ПО ЧИСЛУ ОБЩИХ ЗАПРОСОВ\n{'='*100}")
    print(f"{'сайт A':<26} {'сайт B':<26} {'общих':>7} {'перекр.':>8} {'Жаккар':>7} "
          f"{'показы A':>10} {'показы B':>10}")
    for p in sorted(pairs, key=lambda x: -x["shared"])[:30]:
        print(f"{p['a']:<26} {p['b']:<26} {p['shared']:>7,} {p['overlap']*100:>7.1f}% "
              f"{p['jaccard']*100:>6.1f}% {p['imp_share_a']*100:>9.1f}% {p['imp_share_b']*100:>9.1f}%")

    # ---------- матрица в CSV ----------
    with open(os.path.join(OUT, "peresechenie-matrica.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["сайт A", "сайт B", "запросов A", "запросов B", "общих запросов",
                    "коэф перекрытия %", "Жаккар %", "доля показов A на общих %",
                    "доля показов B на общих %", "показов на общих запросах"])
        for p in sorted(pairs, key=lambda x: -x["shared"]):
            w.writerow([p["a"], p["b"], p["n_a"], p["n_b"], p["shared"],
                        bo.num(p["overlap"]*100, 2), bo.num(p["jaccard"]*100, 2),
                        bo.num(p["imp_share_a"]*100, 2), bo.num(p["imp_share_b"]*100, 2), p["imp_shared"]])

    # квадратная матрица «доля показов A на запросах, что есть и у B»
    with open(os.path.join(OUT, "peresechenie-kvadrat.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["показы строки-сайта на запросах, которые есть и у сайта-столбца, %"] + sites)
        pm = {}
        for p in pairs:
            pm[(p["a"], p["b"])] = p["imp_share_a"]
            pm[(p["b"], p["a"])] = p["imp_share_b"]
        for a in sites:
            w.writerow([a] + [("" if a == b else bo.num(pm.get((a, b), 0)*100)) for b in sites])

    # ---------- самые дорогие спорные запросы ----------
    contested = []
    for q, o in owners.items():
        if len(o) < 2:
            continue
        contested.append((qimp[q], q, sorted(o, key=lambda d: -agg[(d, q)][0])))
    contested.sort(reverse=True)

    print(f"\n{'='*100}\n### ТОП-40 СПОРНЫХ ЗАПРОСОВ (2+ моих сайта, по суммарным показам)\n{'='*100}")
    print(f"{'показы':>8}  запрос / сайты (показы, клики, позиция)")
    for imp, q, ds in contested[:40]:
        parts = []
        for d in ds[:5]:
            i, c, p = agg[(d, q)]
            parts.append(f"{short(d)} {i}/{c}/поз{p:.0f}")
        more = f" +{len(ds)-5}" if len(ds) > 5 else ""
        print(f"{imp:>8,}  {q}\n{'':>10}{' | '.join(parts)}{more}")

    with open(os.path.join(OUT, "spornye-zaprosy.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["запрос", "сайтов", "показов всего", "кликов всего", "сайты (показы/клики/позиция)"])
        for imp, q, ds in contested:
            clk = sum(agg[(d, q)][1] for d in ds)
            det = " | ".join(f"{d} {agg[(d,q)][0]}/{agg[(d,q)][1]}/{bo.num(agg[(d,q)][2])}" for d in ds)
            w.writerow([q, len(ds), imp, clk, det])
    print(f"\nCSV: peresechenie-matrica.csv, peresechenie-kvadrat.csv, "
          f"spornye-zaprosy.csv ({len(contested):,} строк)")

    # ---------- перекрёстная проверка по yq.csv ----------
    yagg = bo.aggregate(rows_y)
    yidx = bo.site_index(yagg)
    ysites, ysets, ypairs = bo.pair_stats(yidx)
    yow = collections.defaultdict(set)
    for (d, q) in yagg:
        yow[q].add(d)
    yd = collections.Counter(len(v) for v in yow.values())
    tq = sum(yd.values())
    print(f"\n{'='*100}\n### ПЕРЕКРЁСТНАЯ ПРОВЕРКА: yq.csv (только Яндекс, 2026-06-18 — 2026-08-17)\n{'='*100}")
    print(f"уникальных запросов {tq:,}; с 2+ сайтами {sum(v for n,v in yd.items() if n>=2):,} "
          f"({sum(v for n,v in yd.items() if n>=2)/tq*100:.1f}%)")
    print(f"{'сайт A':<26} {'сайт B':<26} {'общих':>7} {'перекр.':>8}")
    for p in sorted(ypairs, key=lambda x: -x["overlap"])[:15]:
        print(f"{p['a']:<26} {p['b']:<26} {p['shared']:>7,} {p['overlap']*100:>7.1f}%")


if __name__ == "__main__":
    main()
