# -*- coding: utf-8 -*-
"""Портрет покупателя против портрета базы обзвона.

Вопрос владельца: сколько компаний в базе ПОХОЖИ на тех, кто реально покупает.
Считаем по трём измеримым признакам — ОКВЭД, выручка, регион — и сравниваем
доли: у покупателей против всей базы. Где доля у покупателей заметно выше,
там признак и работает.
"""
import sqlite3
from collections import Counter

СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ОБОГ = r"C:\sender\enrich.db"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def код2(o):
    o = str(o or "").strip()
    return o.split(".")[0][:2] if o and o[0].isdigit() else ""


c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
c.close()

# что знаем про покупателей: обогащение + свежие реквизиты
e = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=60)
e.row_factory = sqlite3.Row
знание = {}
for r in e.execute("SELECT inn, okved, region, revenue_rub, division FROM companies"):
    и = цифры(r["inn"])
    if и:
        знание[и] = {"okved": r["okved"], "region": r["region"],
                     "revenue": r["revenue_rub"], "division": r["division"]}
кол = {x["name"] for x in e.execute("PRAGMA table_info(requisites)")}
поля = [p for p in ("okved", "okved_main", "region", "address", "name") if p in кол]
if поля:
    for r in e.execute("SELECT inn, %s FROM requisites" % ", ".join(поля)):
        и = цифры(r["inn"])
        if not и:
            continue
        з = знание.setdefault(и, {})
        if not з.get("okved"):
            з["okved"] = (r["okved"] if "okved" in поля else None) or \
                         (r["okved_main"] if "okved_main" in поля else None)
        if not з.get("region"):
            з["region"] = (r["region"] if "region" in поля else None) or \
                          (str(r["address"])[:40] if "address" in поля else None)
e.close()

o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН, uri=True, timeout=60)
o.row_factory = sqlite3.Row
база = {}
for r in o.execute("SELECT inn, okved_main, region, revenue_rub FROM obzvon"):
    и = цифры(r["inn"])
    if и:
        база[и] = {"okved": r["okved_main"], "region": r["region"],
                   "revenue": r["revenue_rub"]}
o.close()

пок = {и: знание[и] for и in сделки if и in знание}
print("покупателей с данными: %d из %d; в базе обзвона строк: %d"
      % (len(пок), len(сделки), len(база)))

def доли(строки, ключ, n=14):
    c = Counter()
    для = 0
    for з in строки:
        v = з.get(ключ)
        if ключ == "okved":
            v = код2(v)
        v = str(v or "").strip()
        if not v:
            continue
        для += 1
        c[v] += 1
    return c, для

пок_ок, пок_n = доли(пок.values(), "okved")
баз_ок, баз_n = доли(база.values(), "okved")
print("\n=== ОКВЭД (двузначный раздел): покупатели против базы ===")
print("%-6s %8s %8s %8s %8s   %s" % ("код", "покуп.", "доля", "в базе",
                                     "доля", "во сколько раз"))
строки = []
for код, k in пок_ок.most_common(24):
    дп = 100.0 * k / пок_n
    дб = 100.0 * баз_ок.get(код, 0) / баз_n if баз_n else 0
    строки.append((дп / дб if дб else 99.0, код, k, дп, баз_ок.get(код, 0), дб))
for раз, код, k, дп, kb, дб in sorted(строки, key=lambda x: -x[2])[:16]:
    print("%-6s %8d %7.1f%% %8d %7.1f%%   %.1f×"
          % (код, k, дп, kb, дб, раз))

print("\n=== ВЫРУЧКА ===")
def выр(строки):
    з = []
    for x in строки:
        try:
            v = float(x.get("revenue") or 0)
        except Exception:
            v = 0
        if v > 0:
            з.append(v)
    з.sort()
    return з
вп, вб = выр(пок.values()), выр(база.values())
for имя, з in (("покупатели", вп), ("база обзвона", вб)):
    if not з:
        continue
    print("   %-14s известна у %6d: медиана %8.0f млн, верхний квартиль %8.0f млн"
          % (имя, len(з), з[len(з) // 2] / 1e6, з[int(len(з) * 0.75)] / 1e6))
if вп:
    порог = вп[len(вп) // 4]
    выше = sum(1 for v in вб if v >= порог)
    print("   нижний квартиль покупателей = %.0f млн" % (порог / 1e6))
    print("   компаний базы с выручкой не ниже: %d (%.1f%% от известных)"
          % (выше, 100.0 * выше / len(вб) if вб else 0))

print("\n=== СКОЛЬКО В БАЗЕ ПОХОЖИХ НА ПОКУПАТЕЛЯ ===")
годные_коды = {код for раз, код, k, дп, kb, дб in строки if раз >= 1.5 and k >= 5}
print("   разделов ОКВЭД, где покупатели встречаются в 1.5+ раза чаще: %d"
      % len(годные_коды))
print("   это коды: %s" % ", ".join(sorted(годные_коды)))
похожие = 0
похожие_и_богатые = 0
порог = вп[len(вп) // 4] if вп else 0
for и, з in база.items():
    if код2(з.get("okved")) in годные_коды:
        похожие += 1
        try:
            if float(з.get("revenue") or 0) >= порог:
                похожие_и_богатые += 1
        except Exception:
            pass
print("   компаний базы в этих разделах:                 %d" % похожие)
print("   из них с выручкой не ниже нижнего квартиля:    %d" % похожие_и_богатые)
