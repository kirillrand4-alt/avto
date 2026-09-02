# -*- coding: utf-8 -*-
"""Событие 325345: полный текст входящего от ИМСБ и что с ответом на него."""
import sqlite3

БАЗА = r"C:\sender\sender.db"
ПОЧТА = "secretar@imsb.ru"

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=90)
c.row_factory = sqlite3.Row
табл = [r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]

print("=== ТАБЛИЦЫ, ГДЕ МОЖЕТ БЫТЬ СОБЫТИЕ ===")
print("   " + ", ".join(т for т in табл if any(
    к in т.lower() for к in ("event", "sobyt", "lead", "reply", "otvet",
                             "message", "inbox", "thread"))))

# ищем событие по id во всех таблицах с колонкой id
нашли = []
for т in табл:
    поля = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
    if "id" not in поля:
        continue
    try:
        r = c.execute("SELECT * FROM %s WHERE id=?" % т, (325345,)).fetchone()
    except Exception:                                          # noqa: BLE001
        continue
    if r:
        нашли.append((т, dict(r)))

print("")
print("=== СОБЫТИЕ 325345 ===")
for т, д in нашли:
    print("   таблица %s:" % т)
    for к, v in д.items():
        if v not in (None, ""):
            print("      %-18s %s" % (к, str(v)[:400]))

# всё по этому адресу
print("")
print("=== ВСЁ ПО АДРЕСУ %s ===" % ПОЧТА)
for т in табл:
    поля = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
    поле = next((п for п in поля if п.lower() in
                 ("email", "to_email", "from_email", "address", "recipient_email")),
                None)
    if not поле:
        continue
    try:
        ряды = c.execute("SELECT * FROM %s WHERE %s=? LIMIT 6"
                         % (т, поле), (ПОЧТА,)).fetchall()
    except Exception:                                          # noqa: BLE001
        continue
    if ряды:
        print("")
        print("   --- %s: %d строк ---" % (т, len(ряды)))
        for r in ряды:
            д = {к: str(r[к])[:150] for к in r.keys()
                 if r[к] not in (None, "")}
            print("      %s" % д)
c.close()
