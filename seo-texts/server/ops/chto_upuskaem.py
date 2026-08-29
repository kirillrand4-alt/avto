# -*- coding: utf-8 -*-
"""Что именно упускаем: разбор 3749 компаний со сделкой по нашим базам."""
import sqlite3
from collections import Counter

СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ОБОГ = r"C:\sender\enrich.db"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
получатели = {цифры(r[0]) for r in c.execute(
    "SELECT inn FROM recipients WHERE inn IS NOT NULL")}
c.close()

o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН, uri=True, timeout=60)
o.row_factory = sqlite3.Row
обзвон = {}
for r in o.execute("SELECT inn, name_short, "
                   "       COALESCE(emails_base,'') || ' ' || "
                   "       COALESCE(emails_site,'') AS email, "
                   "       revenue_rub FROM obzvon"):
    и = цифры(r["inn"])
    if и:
        обзвон[и] = r
o.close()

e = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=60)
e.row_factory = sqlite3.Row
обог = {}
for r in e.execute("SELECT inn, COALESCE(short_name,name) nm, best_email, site, "
                   "       revenue_rub, division, okved FROM companies"):
    и = цифры(r["inn"])
    if и:
        обог[и] = r
вне = {цифры(r[0]) for r in e.execute("SELECT inn FROM vne_bazy")}
e.close()

в_обзвоне = сделки & set(обзвон)
в_обог = сделки & set(обог)
нигде = сделки - set(обзвон) - set(обог) - получатели

print("=== ПОКРЫТИЕ ПРОВЕРЕННЫХ ПОКУПАТЕЛЕЙ (%d компаний со сделкой) ===" % len(сделки))
print("   в базе обзвона:      %4d" % len(в_обзвоне))
print("   в обогащении:        %4d" % len(в_обог))
print("   хоть где-то:         %4d (%.1f%%)"
      % (len(сделки) - len(нигде), 100.0 * (len(сделки) - len(нигде)) / len(сделки)))
print("   нигде:               %4d (%.1f%%)"
      % (len(нигде), 100.0 * len(нигде) / len(сделки)))
print("   из «нигде» лежат в vne_bazy: %d" % len(нигде & вне))

с_почтой_обзвон = sum(1 for и in в_обзвоне if (обзвон[и]["email"] or "").strip())
с_почтой_обог = sum(1 for и in в_обог if (обог[и]["best_email"] or "").strip())
print("\n=== МОЖНО ЛИ ИМ ПИСАТЬ ===")
print("   из тех, кто в обзвоне, с почтой:     %d из %d"
      % (с_почтой_обзвон, len(в_обзвоне)))
print("   из тех, кто в обогащении, с почтой:  %d из %d"
      % (с_почтой_обог, len(в_обог)))
print("   уже заведены получателями:           %d" % len(сделки & получатели))
готовы = (в_обзвоне | в_обог) - получатели
с_почтой = {и for и in готовы
            if (обзвон.get(и) or {}).__class__ is not dict and False}
с_почтой = set()
for и in готовы:
    п = (обзвон[и]["email"] if и in обзвон else "") or ""
    б = (обог[и]["best_email"] if и in обог else "") or ""
    if п.strip() or б.strip():
        с_почтой.add(и)
print("   ЗНАЕМ, НО НЕ ЗАВЕЛИ:                 %d, из них с почтой %d"
      % (len(готовы), len(с_почтой)))

print("\n=== ЧТО ЗНАЕМ ПРО ТЕХ, КОГО ЗНАЕМ (направление и выручка) ===")
напр, выручка = Counter(), []
for и in в_обог:
    напр[str(обог[и]["division"] or "—")] += 1
    try:
        в = float(обог[и]["revenue_rub"] or 0)
        if в > 0:
            выручка.append(в)
    except Exception:
        pass
print("   направление: %s" % dict(напр.most_common(6)))
if выручка:
    выручка.sort()
    print("   выручка: медиана %.0f млн, среднее %.0f млн, известна у %d"
          % (выручка[len(выручка) // 2] / 1e6,
             sum(выручка) / len(выручка) / 1e6, len(выручка)))
print("\n=== ПРИМЕРЫ «ЗНАЕМ, НО НЕ ЗАВЕЛИ» ===")
n = 0
for и in sorted(с_почтой):
    имя = (обог[и]["nm"] if и in обог else None) or \
          (обзвон[и]["name_short"] if и in обзвон else "")
    почта = (обог[и]["best_email"] if и in обог else "") or \
            (обзвон[и]["email"] if и in обзвон else "")
    print("   %-13s %-42s %s" % (и, str(имя)[:42], str(почта)[:34]))
    n += 1
    if n >= 12:
        break
