# -*- coding: utf-8 -*-
"""Новые решения предкласса вне групп (14.10): сколько Meyer, какие отрасли/выручка,
примеры. Только чтение."""
import sqlite3
from collections import Counter

e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
e.row_factory = sqlite3.Row
р = [dict(x) for x in e.execute("SELECT inn, name, okved, revenue_rub, verdikt_napr FROM companies "
                                  "WHERE verdikt_pochemu LIKE '%вне групп 14.10%'")]
print("решено вне групп: %d; %s" % (len(р), dict(Counter(x["verdikt_napr"] for x in р).most_common())))
м = [x for x in р if x["verdikt_napr"] in ("мейер", "оба")]
print("ОКВЭД-класс у Meyer:", dict(Counter((x["okved"] or "?")[:2] for x in м).most_common(12)))


def корз(в):
    try:
        в = float(в or 0)
    except (TypeError, ValueError):
        в = 0
    return "нет данных" if в <= 0 else "до 100 млн" if в < 1e8 else "100 млн-1 млрд" if в < 1e9 else "от 1 млрд"


print("выручка у Meyer:", dict(Counter(корз(x["revenue_rub"]) for x in м)))
for x in м[:15]:
    print("   %s | ОКВЭД %s | %s" % (str(x["name"])[:40], x["okved"], корз(x["revenue_rub"])))
print("=== НОВЫЕ MEYER ===")
