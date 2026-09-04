#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сколько сетка реально зарабатывает тем, что занимает несколько мест в выдаче.

Три вопроса:
  A. какую долю живых кликов дают вторые и ниже свои сайты;
  B. ухудшается ли позиция лучшего сайта, когда на запросе стоит много своих;
  C. что дороже — второй слот внизу выдачи или подъём первого сайта на две позиции.
Яндекс, berg-пара исключена: её клики за период накручены (см. README).
"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_overlap as bo

SRC = sys.argv[1] if len(sys.argv) > 1 else "."
BERG = {"berg-compressor.com", "berg-kompressor.ru"}
MIN_IMP = 50

rows = [r for r in bo.load_q_files(SRC) if r[1] == "Яндекс"]
agg = bo.aggregate(rows)

base = collections.defaultdict(lambda: [0, 0])
for d, e, q, c, i, p in rows:
    if d in BERG or i == 0 or p <= 0:
        continue
    base[min(int(round(p)), 50)][0] += i
    base[min(int(round(p)), 50)][1] += c
curve, last = {}, 0.02
for p in range(1, 51):
    i, c = base.get(p, [0, 0])
    curve[p] = (c / i) if i >= 300 else last
    last = curve[p]
ctr = lambda p: curve[min(max(int(round(p)), 1), 50)]

owners = collections.defaultdict(list)
for (d, q), v in agg.items():
    owners[q].append((d, v))

print("=== A. ВКЛАД ВТОРЫХ И НИЖЕ СВОИХ САЙТОВ ===")
tot = sum(v[1] for (d, q), v in agg.items() if d not in BERG)
lead = extra = 0
for q, lst in owners.items():
    lst = [x for x in lst if x[0] not in BERG]
    if len(lst) < 2:
        continue
    s = sorted(lst, key=lambda x: -x[1][0])
    lead += s[0][1][1]
    extra += sum(v[1] for _, v in s[1:])
print(f"живых кликов сети: {tot:,}")
print(f"у лидера на спорных запросах: {lead:,}")
print(f"добавили вторые и ниже: {extra:,} — {extra/tot*100:.1f}% всех кликов сети, "
      f"+{extra/max(lead,1)*100:.0f}% к лидеру на этих запросах")

print("\n=== B. ПОЗИЦИЯ ЛУЧШЕГО ПРИ РАЗНОМ ЧИСЛЕ СВОИХ НА ЗАПРОСЕ ===")
g = collections.defaultdict(lambda: [0, 0, 0, 0.0, 0])
for q, lst in owners.items():
    lst = [x for x in lst if x[0] not in BERG]
    if not lst:
        continue
    i = sum(v[0] for _, v in lst)
    if i < MIN_IMP:
        continue
    best = min((v[2] for _, v in lst if v[2] > 0), default=99)
    n = min(len(lst), 4)
    g[n][0] += 1; g[n][1] += i; g[n][2] += sum(v[1] for _, v in lst)
    g[n][3] += best * i; g[n][4] += 1 if best <= 10 else 0
print(f"{'своих на запросе':<18}{'запросов':>10}{'показов':>10}{'кликов':>8}{'CTR':>7}"
      f"{'поз. лучшего':>14}{'лучший в топ-10':>17}")
for n in sorted(g):
    qn, i, c, pw, t = g[n]
    print(f"{(str(n) if n < 4 else '4+'):<18}{qn:>10,}{i:>10,}{c:>8,}"
          f"{c/i*100:>6.1f}%{pw/i:>14.1f}{t/qn*100:>16.0f}%")
print("связь корреляционная: запросы с большим числом своих сайтов — это ВЧ-запросы,")
print("у них своя механика CTR. Вывод осторожный: падения позиции лучшего не видно.")

print("\n=== C. ВТОРОЙ СЛОТ ПРОТИВ ПОДЪЁМА ПЕРВОГО ===")
print("  CTR: " + ", ".join(f"поз{p} {ctr(p)*100:.1f}%" for p in (1, 3, 5, 8, 10, 15, 20)))
for first in (3, 5, 8):
    up = ctr(max(first - 2, 1)) - ctr(first)
    for second in (8, 12, 20):
        if second <= first:
            continue
        print(f"  первый на {first:>2}: второй сайт на {second:>2} даёт +{ctr(second)*100:4.1f} п.п. | "
              f"поднять первого на {max(first-2,1):>2} даёт +{up*100:4.1f} п.п.")
