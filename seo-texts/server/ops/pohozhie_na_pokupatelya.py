# -*- coding: utf-8 -*-
"""Из чего состоят «похожие на покупателя» и скольким из них мы ещё не писали."""
import sqlite3
from collections import Counter

СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ГОДНЫЕ = {"01", "10", "16", "19", "20", "22", "23", "24", "28", "30", "33",
          "41", "46", "47", "52", "70"}
ПОРОГ = 106e6


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


def код2(o):
    o = str(o or "").strip()
    return o.split(".")[0][:2] if o and o[0].isdigit() else ""


c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
писали = {цифры(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.sent_at IS NOT NULL AND r.inn IS NOT NULL")}
получатели = {цифры(r[0]) for r in c.execute(
    "SELECT inn FROM recipients WHERE inn IS NOT NULL")}
стоп = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE scope='inn'")}
c.close()

o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН, uri=True, timeout=60)
o.row_factory = sqlite3.Row
по_разделам = Counter()
богатые = Counter()
цель = []
for r in o.execute("SELECT inn, name_short, okved_main, revenue_rub, "
                   "       COALESCE(emails_base,'') || ' ' || "
                   "       COALESCE(emails_site,'') AS mails FROM obzvon"):
    и = цифры(r["inn"])
    к = код2(r["okved_main"])
    if not и or к not in ГОДНЫЕ:
        continue
    по_разделам[к] += 1
    try:
        в = float(r["revenue_rub"] or 0)
    except Exception:
        в = 0
    if в >= ПОРОГ:
        богатые[к] += 1
        цель.append((и, r["name_short"], к, в, (r["mails"] or "").strip()))
o.close()

print("=== ПОХОЖИЕ НА ПОКУПАТЕЛЯ В БАЗЕ ОБЗВОНА ===")
print("%-6s %10s %10s" % ("раздел", "всего", "с выручкой ≥106 млн"))
for к, n in по_разделам.most_common():
    print("%-6s %10d %10d" % (к, n, богатые.get(к, 0)))
print("   ИТОГО %d, из них крупных %d"
      % (sum(по_разделам.values()), sum(богатые.values())))

сцелью = {и for и, _, _, _, _ in цель}
print("\n=== ЧТО С НИМИ УЖЕ СДЕЛАНО ===")
print("   заведены получателями:      %d" % len(сцелью & получатели))
print("   писали хоть раз:            %d" % len(сцелью & писали))
print("   в стоп-листе (сделка и др.): %d" % len(сцелью & стоп))
свежие = сцелью - получатели - стоп
print("   НЕ ТРОНУТЫ ВООБЩЕ:          %d" % len(свежие))
с_почтой = {и for и, _, _, _, m in цель if и in свежие and "@" in m}
print("   из них с почтой в базе:     %d" % len(с_почтой))

print("\n=== 12 ПРИМЕРОВ НЕТРОНУТЫХ ===")
n = 0
for и, имя, к, в, m in sorted(цель, key=lambda x: -x[3]):
    if и not in с_почтой:
        continue
    print("   %-13s %-40s ОКВЭД %s  %6.0f млн  %s"
          % (и, str(имя)[:40], к, в / 1e6, m.split("|")[0].strip()[:28]))
    n += 1
    if n >= 12:
        break
