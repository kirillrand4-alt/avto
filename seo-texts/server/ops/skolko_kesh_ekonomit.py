# -*- coding: utf-8 -*-
"""Сколько кэш экономит НА САМОМ ДЕЛЕ — по журналу настоящих прогонов.

Вопрос владельца «мы так и не сможем использовать кэш?» стоит мерить не
пробой на двух вызовах, а тем, что уже накоплено: сколько токенов прошло
записью в кэш, сколько чтением, и во что это обошлось против цены тех же
токенов без кэша.

Ставки шлюза: запись 1.25 обычного входа, чтение 0.10.
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

ЖУРНАЛЫ = [r"C:\sender\_ops\gen-partiya-935.jsonl",
           r"C:\sender\_ops\rezenzii-pisem.jsonl"]
ЦЕНА = {"opus": (15.0, 75.0), "sonnet": (3.0, 15.0)}


def тариф(модель):
    м = str(модель or "").lower()
    if "sonnet" in м or "haiku" in м:
        return ЦЕНА["sonnet"], "sonnet"
    return ЦЕНА["opus"], "opus"


расход = defaultdict(Counter)
строк = Counter()
for путь in ЖУРНАЛЫ:
    if not os.path.exists(путь):
        print(f"нет журнала: {путь}")
        continue
    for s in io.open(путь, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                              # noqa: BLE001
            continue
        for ключ in ("расход", "usage", "счёт"):
            u = z.get(ключ)
            if isinstance(u, dict):
                break
        else:
            u = None
        if not isinstance(u, dict):
            continue
        м = str(z.get("модель") or z.get("model") or "?")
        строк[м] += 1
        for k in ("in", "out", "cw", "cr"):
            if u.get(k):
                расход[м][k] += int(u[k])

if not расход:
    print("в журналах нет разбивки по токенам — считать нечего")
    raise SystemExit(0)

print(f"{'модель':<22} {'вызовов':>8} {'вход':>12} {'запись кэша':>13} "
      f"{'чтение кэша':>13}")
итог = Counter()
for м, r in sorted(расход.items(), key=lambda t: -sum(t[1].values())):
    print(f"{м:<22} {строк[м]:>8} {r['in']:>12} {r['cw']:>13} {r['cr']:>13}")
    for k, v in r.items():
        итог[k] += v

print(f"\n{'ВСЕГО':<22} {sum(строк.values()):>8} {итог['in']:>12} "
      f"{итог['cw']:>13} {итог['cr']:>13}")

print("\n== что кэш дал деньгами ==")
для_всех = 0.0
без_кэша = 0.0
for м, r in расход.items():
    (вх_ст, вых_ст), _ = тариф(м)
    факт = ((r["in"] + 1.25 * r["cw"] + 0.10 * r["cr"]) / 1e6 * вх_ст
            + r["out"] / 1e6 * вых_ст)
    # без кэша те же токены прошли бы обычным входом по ставке 1.0
    альт = ((r["in"] + r["cw"] + r["cr"]) / 1e6 * вх_ст
            + r["out"] / 1e6 * вых_ст)
    для_всех += факт
    без_кэша += альт
print(f"  фактически потрачено:      ${для_всех:,.2f}")
print(f"  стоило бы без кэша вообще: ${без_кэша:,.2f}")
разница = без_кэша - для_всех
знак = "экономия" if разница > 0 else "ПЕРЕПЛАТА"
print(f"  {знак}: ${abs(разница):,.2f}"
      + (f" ({abs(разница)/без_кэша*100:.1f}%)" if без_кэша else ""))
print("\n  (запись в кэш дороже обычного входа в 1.25 раза: если записи много,"
      "\n   а чтения нет, кэш не экономит, а удорожает — это и видно ниже)")
for м, r in расход.items():
    if r["cw"] and not r["cr"]:
        print(f"  ! {м}: записано {r['cw']}, прочитано 0 — чистая переплата")
    elif r["cr"]:
        print(f"  + {м}: прочитано {r['cr']} из записанных {r['cw']} "
              f"({r['cr']/max(1,r['cw']):.1f}x)")
