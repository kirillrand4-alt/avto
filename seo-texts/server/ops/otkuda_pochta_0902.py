# -*- coding: utf-8 -*-
"""Только чтение: откуда на самом деле взяты адреса «с сайта»."""
import re
import sqlite3

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row

print("=== КОНКРЕТНО gyumri_cheese@mail.ru ===")
for р in e.execute("SELECT inn, email, source, source_url, razdel, addr_class,"
                   " updated_at FROM emails WHERE email='gyumri_cheese@mail.ru'"):
    print("  инн=%s источник=%s" % (р["inn"], р["source"]))
    print("  ссылка: %s" % р["source_url"])
    print("  раздел=%s класс=%s обновлено=%s"
          % (р["razdel"], р["addr_class"], str(р["updated_at"])[:19]))
об = e.execute("SELECT name, site, cand_site, site_checko, best_email FROM companies"
               " WHERE inn='0101007605'").fetchone()
if об:
    print("  компания: %s" % об["name"])
    print("  сайт=%s cand=%s checko=%s" % (об["site"], об["cand_site"],
                                           об["site_checko"]))

print("\n=== ЧТО ВООБЩЕ В source_url У ИСТОЧНИКА own-site ===")
дом = {}
n = 0
for р in e.execute("SELECT source_url FROM emails WHERE source='own-site'"
                   " AND source_url IS NOT NULL AND source_url<>'' LIMIT 40000"):
    u = str(р["source_url"]).lower()
    m = re.sub(r"^https?://", "", u).split("/")[0].replace("www.", "")
    дом[m] = дом.get(m, 0) + 1
    n += 1
print("  разобрано ссылок: %d, разных доменов: %d" % (n, len(дом)))
print("  топ доменов в ссылках:")
for д, k in sorted(дом.items(), key=lambda x: -x[1])[:12]:
    print("    %-34s %d" % (д[:34], k))
агр = sum(k for д, k in дом.items()
          if any(a in д for a in ("checko", "rusprofile", "list-org", "zachestny",
                                  "sbis", "audit-it", "e-ecolog", "vypiska")))
print("  из них с агрегаторов (checko, rusprofile и подобные): %d" % агр)

print("\n=== ПУСТЫЕ ССЫЛКИ ===")
всего = e.execute("SELECT COUNT(*) FROM emails WHERE source='own-site'").fetchone()[0]
без = e.execute("SELECT COUNT(*) FROM emails WHERE source='own-site'"
                " AND (source_url IS NULL OR source_url='')").fetchone()[0]
print("  own-site всего %d, из них без ссылки %d" % (всего, без))
