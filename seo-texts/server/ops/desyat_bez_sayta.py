# -*- coding: utf-8 -*-
"""Десять компаний, у которых ходилка сайта не нашла — со ссылками на Чеко."""
import io
import json
import sqlite3

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=120)
карточки = {}
for и, о, н, к in c.execute(
        "SELECT inn, ogrn, name_short, okved_main FROM requisites "
        " WHERE src='checko-sbor-agro'"):
    карточки[str(и)] = (str(о or ""), str(н or ""), str(к or ""))
c.close()

взяли = []
for с in io.open(r"C:\sender\server\checko_finansy.jsonl", encoding="utf-8",
                 errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        z = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if z.get("сбой"):
        continue
    и = str(z.get("inn") or "")
    if и not in карточки:
        continue
    if str(z.get("site_checko") or "").strip():
        continue
    тел = str(z.get("phones_checko") or "").strip()
    почта = str(z.get("emails_checko") or "").strip()
    if not (тел or почта):
        continue
    try:
        выр = int(str(z.get("revenue_rub") or "0") or 0)
    except ValueError:
        выр = 0
    if выр < 30_000_000:
        continue
    огрн, имя, квэд = карточки[и]
    взяли.append((выр, и, огрн, имя, квэд, тел, почта))
    if len(взяли) >= 40:
        break

взяли.sort(reverse=True)

print("=" * 92)
print("=== ДЕСЯТЬ КОМПАНИЙ БЕЗ САЙТА (выручка от 30 млн, контакты есть) ===")
print("")
for выр, и, огрн, имя, квэд, тел, почта in взяли[:10]:
    print("%s" % имя[:60])
    print("   ИНН %-13s выручка %-18s ОКВЭД %s"
          % (и, format(выр, ",d"), квэд[:40]))
    print("   телефон: %s" % (тел[:60] or "—"))
    print("   почта:   %s" % (почта[:60] or "—"))
    print("   https://checko.ru/company/%s/contacts" % огрн)
    print("")
