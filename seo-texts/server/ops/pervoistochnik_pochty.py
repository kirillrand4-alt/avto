# -*- coding: utf-8 -*-
"""Первоисточник адреса: таблица emails и карточка компании. Сводка в конце."""
import json
import sqlite3

ПОЧТА = "marushkiiin@yandex.ru"
ИНН = "7842186599"

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
c.row_factory = sqlite3.Row

письма = [dict(r) for r in c.execute(
    "SELECT * FROM emails WHERE email=? OR inn=?", (ПОЧТА, ИНН))]
компания = c.execute("SELECT * FROM companies WHERE inn=?", (ИНН,)).fetchone()
реквизиты = c.execute("SELECT * FROM requisites WHERE inn=?", (ИНН,)).fetchone()
c.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row
получатель = s.execute("SELECT * FROM recipients WHERE email=?",
                       (ПОЧТА,)).fetchone()
согласие = [dict(r) for r in s.execute(
    "SELECT * FROM consent_log WHERE email=?", (ПОЧТА,))]
s.close()

print("=" * 80)
print("=== СВОДКА: ОТКУДА У НАС АДРЕС %s ===" % ПОЧТА)
print("")
print("--- строки в enrich.emails (%d) ---" % len(письма))
for п in письма:
    for к in ("email", "inn", "source", "istochnik", "src", "role", "person",
              "url", "page", "found_at", "created_at", "updated_at",
              "probe_verdict", "note"):
        if п.get(к) not in (None, ""):
            print("   %-18s %s" % (к, str(п[к])[:150]))
    print("   " + "-" * 40)

print("")
print("--- карточка компании enrich.companies ---")
if компания:
    for к in ("inn", "name", "division", "okved", "site", "cand_site",
              "best_email", "phones", "site_source", "istochnik_kompanii",
              "istochnik_rekvizitov", "nash_priznak", "nash_dokaz",
              "verified_url", "site_checko", "updated_at"):
        if компания[к] if к in компания.keys() else None:
            print("   %-22s %s" % (к, str(компания[к])[:150]))
else:
    print("   компании нет в companies")

print("")
print("--- строка в requisites (данные Чеко) ---")
if реквизиты:
    for к in ("inn", "src", "emails_checko", "phones_checko", "site_checko",
              "name_short", "updated_at"):
        if к in реквизиты.keys() and реквизиты[к] not in (None, ""):
            print("   %-18s %s" % (к, str(реквизиты[к])[:150]))
else:
    print("   в requisites нет")

print("")
print("--- карточка получателя в панели ---")
if получатель:
    for к in ("id", "inn", "email", "company_name", "source", "extra_json",
              "created_at"):
        if к in получатель.keys() and получатель[к] not in (None, ""):
            print("   %-14s %s" % (к, str(получатель[к])[:220]))
print("")
print("--- основание отправки (consent_log) ---")
for з in согласие:
    print("   действие %s | основание %s | источник %s | %s"
          % (з.get("action"), з.get("basis"), з.get("source"),
             з.get("created_at")))
