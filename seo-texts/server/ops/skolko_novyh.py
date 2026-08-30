# -*- coding: utf-8 -*-
"""Сколько из собранного действительно НОВОЕ для наших баз."""
import csv
import io
import sqlite3
from collections import Counter

CSV = r"C:\seostat\Parser2\data\agro-base.csv"
МУСОР = {"46.90"}


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


собрано, мусорных = {}, 0
with io.open(CSV, encoding="utf-8-sig", errors="ignore", newline="") as f:
    for ряд in csv.DictReader(f, delimiter=";"):
        и = цифры(ряд.get("ИНН"))
        к = str(ряд.get("Основной ОКВЭД") or "").strip().split()[0] \
            if str(ряд.get("Основной ОКВЭД") or "").strip() else ""
        if not и:
            continue
        if к in МУСОР:
            мусорных += 1
            continue
        собрано[и] = к
print("строк в файле полезных (без 46.90): %d, уникальных ИНН: %d; мусорных: %d"
      % (len(собрано), len(set(собрано)), мусорных))

o = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\obzvon-index.db", uri=True,
                    timeout=60)
обзвон = {цифры(r[0]) for r in o.execute("SELECT inn FROM obzvon")}
o.close()
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=60)
компании = {цифры(r[0]) for r in e.execute("SELECT inn FROM companies")}
реквизиты = {цифры(r[0]) for r in e.execute(
    "SELECT inn FROM requisites WHERE COALESCE(ogrn,'')<>''")}
e.close()
s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=60)
получатели = {цифры(r[0]) for r in s.execute(
    "SELECT inn FROM recipients WHERE inn IS NOT NULL")}
писали = {цифры(r[0]) for r in s.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.sent_at IS NOT NULL AND r.inn IS NOT NULL")}
s.close()

наши = обзвон | компании | реквизиты | получатели
ключи = set(собрано)
новые = ключи - наши
print("\n=== ПЕРЕСЕЧЕНИЕ С НАШИМИ БАЗАМИ ===")
print("   уже в базе обзвона:        %d" % len(ключи & обзвон))
print("   уже в обогащении:          %d" % len(ключи & компании))
print("   уже в реквизитах:          %d" % len(ключи & реквизиты))
print("   заведены получателями:     %d" % len(ключи & получатели))
print("   писали хоть раз:           %d" % len(ключи & писали))
print("   ---")
print("   НОВЫЕ (нигде не было):     %d из %d (%.1f%%)"
      % (len(новые), len(ключи), 100.0 * len(новые) / len(ключи)))
по_коду = Counter(собрано[и] for и in новые)
print("\nновые по кодам (топ-12):")
for к, n in по_коду.most_common(12):
    print("   %-10s %6d" % (к, n))
