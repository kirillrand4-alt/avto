# -*- coding: utf-8 -*-
"""У скольких целей УЖЕ есть почта от Чеко — то есть писать можно без сайта.

Для письма нужен АДРЕС, а не сайт. Сайт нужен только паспорту, который
делает письмо точнее. Если почта у большинства уже есть, поиск сайтов —
улучшение качества, а не условие работы, и очерёдность трат меняется.
"""
import io
import json
import re
from collections import Counter

ЦЕЛИ = r"C:\seostat\drop\celi_meyer_30mln.jsonl"

счёт = Counter()
примеры = []
почт_всего = 0
for с in io.open(ЦЕЛИ, encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    почты = [p.strip() for p in re.split(r"[|,;]", str(z.get("emails") or ""))
             if "@" in p]
    тел = [t for t in re.split(r"[|,;]", str(z.get("phones") or ""))
           if t.strip()]
    почт_всего += len(почты)
    if почты and тел:
        к = "почта И телефон"
    elif почты:
        к = "только почта"
    elif тел:
        к = "только телефон"
    else:
        к = "ни почты, ни телефона"
    счёт[к] += 1
    if почты and len(примеры) < 8:
        примеры.append("%-34s %s  (%s руб)"
                       % (str(z.get("poln") or "")[:34], почты[0][:34],
                          format(int(z.get("revenue_rub") or 0), ",d")))

итог = sum(счёт.values())
с_почтой = счёт["почта И телефон"] + счёт["только почта"]

print("=" * 78)
print("=== СВОДКА: НУЖЕН ЛИ САЙТ, ЧТОБЫ ПИСАТЬ ===")
print("целей (мейер, от 30 млн, без сайта): %d" % итог)
print("")
for к, в in счёт.most_common():
    print("   %-24s %6d  (%4.1f%%)" % (к, в, 100.0 * в / итог if итог else 0))
print("")
print("ПОЧТА УЖЕ ЕСТЬ У %d КОМПАНИЙ (%.1f%%), всего адресов %d"
      % (с_почтой, 100.0 * с_почтой / итог if итог else 0, почт_всего))
print("")
print("примеры:")
for с in примеры:
    print("   " + с)
