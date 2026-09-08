# -*- coding: utf-8 -*-
"""Только чтение: схема recipients, поиск Чистозерья, исходник возврата в ленту."""
import io
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== СХЕМА recipients ===")
поля = [р["name"] for р in c.execute("PRAGMA table_info(recipients)")]
print("  " + ", ".join(поля))

усл = " OR ".join("%s LIKE ?" % п for п in поля
                  if п in ("email", "name", "company_name", "org", "domain",
                           "site", "inn", "title"))
пар = []
for п in поля:
    if п in ("email", "name", "company_name", "org", "domain", "site", "inn",
             "title"):
        пар.append("%истозерь%")
print("\n=== ПОИСК ПО recipients ===")
найдены = []
for шаблон in ("%chistozer%", "%истозерь%", "%gnezdalova%"):
    q = "SELECT * FROM recipients WHERE " + " OR ".join(
        "IFNULL(%s,'') LIKE ?" % п for п in поля
        if п in ("email", "name", "company_name", "org", "domain", "site",
                 "inn", "title"))
    n = q.count("?")
    for р in c.execute(q, [шаблон] * n):
        найдены.append(dict(р))
        print("  %s" % {к: v for к, v in dict(р).items() if v})
if not найдены:
    print("  ничего")

print("\n=== ПОИСК ПО emails/companies в enrich ===")
try:
    e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
    e.row_factory = sqlite3.Row
    for р in e.execute("SELECT inn, name, site, region, revenue_rub FROM companies"
                       " WHERE name LIKE '%ИСТОЗЕРЬ%' OR site LIKE '%chistozer%'"):
        print("  %s | %s | %s | %s" % (р["inn"], р["name"], р["site"], р["region"]))
    for р in e.execute("SELECT inn, email, source FROM emails"
                       " WHERE email LIKE '%chistozer%'"
                       " OR email LIKE '%gnezdalova%' LIMIT 10"):
        print("  почта: %s %s (%s)" % (р["inn"], р["email"], р["source"]))
except Exception as ex:
    print("  ошибка:", ex)

print("\n" + "=" * 30 + " vernut_lid_v_lentu.py " + "=" * 30)
print(io.open(r"C:\sender\server\ops\vernut_lid_v_lentu.py",
              encoding="utf-8", errors="ignore").read()[:4500])
