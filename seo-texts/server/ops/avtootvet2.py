# -*- coding: utf-8 -*-
"""Найти автоответ АГРО-ХОРС: сначала схема, потом поиск по тексту."""
import re, sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

КУСОК = "15 июля 2026"
store = Store(r"C:\sender\sender.db")
АДРЕС = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
with store._lock:
    for т in ("leads", "lead_events"):
        кол = [c[1] for c in store._conn.execute("PRAGMA table_info(%s)" % т)]
        print("%s: %s" % (т, ", ".join(кол)))
    # ищем по тексту в обеих таблицах
    for т in ("lead_events", "leads"):
        кол = [c[1] for c in store._conn.execute("PRAGMA table_info(%s)" % т)]
        for c in кол:
            try:
                строки = store._conn.execute(
                    "SELECT * FROM %s WHERE %s LIKE ? LIMIT 3"
                    % (т, c), ("%" + КУСОК + "%",)).fetchall()
            except Exception:                                   # noqa: BLE001
                continue
            for р in строки:
                print("")
                print("=" * 74)
                print("НАЙДЕНО: %s.%s" % (т, c))
                for k in кол:
                    з = р[k]
                    if isinstance(з, str) and len(з) > 60:
                        print("   --- %s ---" % k)
                        print(з[:2000])
                    elif з not in (None, ""):
                        print("   %-14s %s" % (k, str(з)[:90]))
                целиком = " ".join(str(р[k] or "") for k in кол
                                   if isinstance(р[k], str))
                чужие = [a for a in sorted(set(АДРЕС.findall(целиком)))
                         if not any(d in a for d in
                                    ("optic-sort", "zernosort", "sort-systems",
                                     "food-sort", "sorting-systems", "rentgen",
                                     "optical-sort", "inspection-systems"))]
                print("   АДРЕСА В ТЕКСТЕ: %s" % (", ".join(чужие) or "нет"))
                raise SystemExit(0)
print("по куску %r ничего не нашлось" % КУСОК)
