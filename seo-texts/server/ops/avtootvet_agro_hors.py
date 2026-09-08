# -*- coding: utf-8 -*-
"""Полный текст автоответа от АГРО-ХОРС и что в нём за адреса."""
import re, sys
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ИНН = "6316219819"
ПОЧТА = "agro-hors@yandex.ru"
АДРЕС = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
store = Store(r"C:\sender\sender.db")
with store._lock:
    таблицы = [r[0] for r in store._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    print("таблицы с лидами: %s"
          % ", ".join(t for t in таблицы if "lead" in t or "event" in t))
    for т in ("lead_events", "events", "leads"):
        if т not in таблицы:
            continue
        кол = [c[1] for c in store._conn.execute("PRAGMA table_info(%s)" % т)]
        текстовые = [c for c in кол if c in
                     ("body", "text", "snippet", "detail", "payload",
                      "message", "content", "reply_text", "last_reply")]
        if not текстовые:
            continue
        усл = " OR ".join("%s LIKE ?" % c for c in кол
                          if c in ("email", "inn", "contact", "from_email"))
        пар = tuple((ПОЧТА if c == "email" or "email" in c else ИНН)
                    for c in кол if c in ("email", "inn", "contact", "from_email"))
        if not усл:
            continue
        try:
            строки = store._conn.execute(
                "SELECT * FROM %s WHERE %s ORDER BY rowid DESC LIMIT 5"
                % (т, усл), пар).fetchall()
        except Exception as ex:                                 # noqa: BLE001
            print("   %s: %s" % (т, str(ex)[:80]))
            continue
        for р in строки:
            print("")
            print("=" * 74)
            print("таблица %s, строка %s" % (т, р["id"] if "id" in кол else "?"))
            for c in кол:
                з = р[c]
                if isinstance(з, str) and len(з) > 40:
                    print("   --- %s ---" % c)
                    print(з[:2500])
                elif з not in (None, ""):
                    print("   %-16s %s" % (c, str(з)[:80]))
            целиком = " ".join(str(р[c] or "") for c in кол
                               if isinstance(р[c], str))
            наш = {"agro-hors@yandex.ru"}
            найдено = [a for a in set(АДРЕС.findall(целиком))
                       if a.lower() not in наш
                       and not any(d in a for d in ("optic-sort", "zernosort",
                                                    "sort-systems", "food-sort",
                                                    "sorting-systems", "rentgen",
                                                    "optical-sort", "inspection"))]
            if найдено:
                print("   АДРЕСА В ТЕКСТЕ: %s" % ", ".join(найдено))
