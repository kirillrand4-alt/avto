# -*- coding: utf-8 -*-
"""Только чтение: читался ли кэш промпта в сегодняшнем прогоне."""
import io
import json
import os
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
стр = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            стр.append(json.loads(s))
        except Exception:
            pass
сег = [z for z in стр if str(z.get("день")) == "2026-08-31"
       and str(z.get("направление")) == "meyer" and z.get("этап") != "итог"]

print("=== ПО МОДЕЛЯМ: кэш записан / прочитан ===")
по_мод = {}
for z in сег:
    м = str(z.get("модель"))
    a = по_мод.setdefault(м, [0, 0, 0])
    a[0] += 1
    a[1] += int(z.get("вход_кэш_запись") or 0)
    a[2] += int(z.get("вход_кэш_чтение") or 0)
print("  %-24s %6s %14s %14s" % ("модель", "строк", "кэш ЗАПИСЬ", "кэш ЧТЕНИЕ"))
for м, (n, зап, чт) in sorted(по_мод.items(), key=lambda x: -x[1][0]):
    print("  %-24s %6d %14d %14d" % (м, n, зап, чт))

хвост = сег[-109:]
зап = sum(int(z.get("вход_кэш_запись") or 0) for z in хвост)
чт = sum(int(z.get("вход_кэш_чтение") or 0) for z in хвост)
print("\n=== ЭТОТ ПРОГОН (последние 109) ===")
print("  кэш записано токенов : %d" % зап)
print("  кэш прочитано токенов: %d" % чт)
print("  доля чтения от записи: %.1f%%" % (100.0 * чт / max(1, зап)))

print("\n=== ИТОГ ===")
if чт == 0 and зап > 0:
    print("  КЭШ ПИШЕТСЯ, НО НЕ ЧИТАЕТСЯ — платим за запись, выгоды ноль.")
    print("  Запись кэша стоит дороже обычного входа, то есть это чистый убыток.")
else:
    print("  чтение кэша: %d токенов" % чт)
