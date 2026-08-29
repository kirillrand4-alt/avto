# -*- coding: utf-8 -*-
"""Портрет покупателя на ПОЛНОМ списке сделок — по журналу добора.

Журнал (sdelki-rekvizity.jsonl) содержит okved_main, адрес и статус на все
3606 карточек; в базу они ещё доливаются, но ждать её незачем — считаем прямо
из журнала, дополняя тем, что уже лежит в companies.
"""
import io
import json
import sqlite3
from collections import Counter

СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ОБОГ = r"C:\sender\enrich.db"
ЖУРНАЛ = r"C:\sender\_ops\sdelki-rekvizity.jsonl"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def код2(o):
    o = str(o or "").strip()
    return o.split(".")[0][:2] if o and o[0].isdigit() else ""


def регион(адрес):
    а = str(адрес or "")
    for разд in (",",):
        часть = а.split(разд)[0].strip()
        if часть:
            return часть[:34]
    return ""


c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
c.close()

знание = {}
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="ignore"):
    с = с.strip()
    if not с:
        continue
    try:
        d = json.loads(с)
    except Exception:                                              # noqa: BLE001
        continue
    и = цифры(d.get("inn"))
    if и:
        знание[и] = {"okved": d.get("okved_main"), "region": регион(d.get("address")),
                     "status": d.get("status"), "revenue": None,
                     "name": d.get("name_short")}
e = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=60)
e.row_factory = sqlite3.Row
for r in e.execute("SELECT inn, okved, region, revenue_rub, division, "
                   "       COALESCE(short_name,name) nm FROM companies"):
    и = цифры(r["inn"])
    if not и:
        continue
    з = знание.setdefault(и, {})
    з["okved"] = з.get("okved") or r["okved"]
    з["region"] = з.get("region") or r["region"]
    з["revenue"] = r["revenue_rub"]
    з["division"] = r["division"]
    з["name"] = з.get("name") or r["nm"]
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
живые = sum(1 for з in пок.values() if str(з.get("status") or "") == "ACTIVE")
print("=== ОСНОВАНИЕ ===")
print("   компаний со сделкой: %d, с данными: %d (%.0f%%), из них ACTIVE: %d"
      % (len(сделки), len(пок), 100.0 * len(пок) / len(сделки), живые))


def доли(строки):
    c = Counter()
    n = 0
    for з in строки:
        к = код2(з.get("okved"))
        if к:
            c[к] += 1
            n += 1
    return c, n


пок_ок, пок_n = доли(пок.values())
баз_ок, баз_n = доли(база.values())
print("   ОКВЭД известен: у покупателей %d, в базе %d" % (пок_n, баз_n))
print("\n=== ОКВЭД: ПОКУПАТЕЛИ ПРОТИВ БАЗЫ ===")
print("%-5s %7s %8s %8s %8s %8s  %s"
      % ("код", "покуп", "доля", "в базе", "доля", "раз", "что это"))
ИМЕНА = {"01": "сельское хозяйство", "10": "пищевые продукты",
         "46": "оптовая торговля", "52": "склады и логистика",
         "25": "металлоизделия", "42": "инженерные сооружения",
         "43": "строительные работы", "72": "научные исследования",
         "20": "химия", "24": "металлургия", "23": "стройматериалы",
         "11": "напитки", "22": "резина и пластмасса", "28": "машины",
         "47": "розница", "41": "здания", "70": "управление",
         "30": "прочий транспорт", "19": "нефтепродукты", "16": "дерево",
         "33": "ремонт машин", "35": "энергия", "68": "недвижимость"}
ряды = []
for код, k in пок_ок.most_common(30):
    дп = 100.0 * k / пок_n
    дб = 100.0 * баз_ок.get(код, 0) / баз_n if баз_n else 0
    ряды.append((код, k, дп, баз_ок.get(код, 0), дб, (дп / дб) if дб else 999.0))
for код, k, дп, kb, дб, раз in ряды[:14]:
    print("%-5s %7d %7.1f%% %8d %7.1f%% %7s  %s"
          % (код, k, дп, kb, дб, ("%.1f×" % раз) if раз < 999 else "—",
             ИМЕНА.get(код, "")))
print("\n   для сравнения, чем набита база:")
for код, k in баз_ок.most_common(6):
    дб = 100.0 * k / баз_n
    дп = 100.0 * пок_ок.get(код, 0) / пок_n
    print("      %-5s %6d %5.1f%% базы, у покупателей %5.1f%%  %s"
          % (код, k, дб, дп, ИМЕНА.get(код, "")))

print("\n=== НАПРАВЛЕНИЕ (по карточке обогащения) ===")
напр = Counter(str(з.get("division") or "не решено") for з in пок.values())
for н, k in напр.most_common():
    print("   %-12s %d" % (н, k))

print("\n=== РЕГИОНЫ ПОКУПАТЕЛЕЙ (топ-10) ===")
рег = Counter(str(з.get("region") or "").strip() for з in пок.values()
              if str(з.get("region") or "").strip())
for р, k in рег.most_common(10):
    print("   %-36s %d" % (р[:36], k))
