# -*- coding: utf-8 -*-
"""Только чтение: у скольких адресов ссылка ведёт на СОБСТВЕННЫЙ сайт компании."""
import re
import sqlite3

e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row


def дом(u):
    u = str(u or "").strip().lower()
    if not u:
        return ""
    u = re.sub(r"^https?://", "", u).split("/")[0].split("?")[0]
    return u[4:] if u.startswith("www.") else u


print("=== ЧТО ТАКОЕ che-cko.ru ===")
for р in e.execute("SELECT inn, email, source_url FROM emails"
                   " WHERE source_url LIKE '%che-cko%' LIMIT 3"):
    print("  инн=%s %s <- %s" % (р["inn"], р["email"], str(р["source_url"])[:70]))
    об = e.execute("SELECT name, site FROM companies WHERE inn=?",
                   (р["inn"],)).fetchone()
    if об:
        print("      компания %s, её сайт %s" % (str(об["name"])[:40], об["site"]))

print("\n=== СВЕРКА ССЫЛКИ С СОБСТВЕННЫМ САЙТОМ (вся база own-site) ===")
свои = чужие = нет_сайта = 0
чужие_домены = {}
for р in e.execute("SELECT e.inn, e.source_url, c.site, c.cand_site, c.site_checko"
                   " FROM emails e JOIN companies c ON c.inn=e.inn"
                   " WHERE e.source='own-site' AND e.source_url<>''"):
    д = дом(р["source_url"])
    наши = {дом(р["site"]), дом(р["cand_site"]), дом(р["site_checko"])} - {""}
    if not наши:
        нет_сайта += 1
    elif д in наши:
        свои += 1
    else:
        чужие += 1
        чужие_домены[д] = чужие_домены.get(д, 0) + 1
итого = свои + чужие + нет_сайта
print("  всего адресов own-site со ссылкой: %d" % итого)
print("  ссылка на собственный сайт компании: %d (%.0f%%)"
      % (свои, 100.0 * свои / max(1, итого)))
print("  ссылка на ЧУЖОЙ домен:              %d (%.0f%%)"
      % (чужие, 100.0 * чужие / max(1, итого)))
print("  у компании сайт не записан:         %d (%.0f%%)"
      % (нет_сайта, 100.0 * нет_сайта / max(1, итого)))
print("\n  топ чужих доменов:")
for д, k in sorted(чужие_домены.items(), key=lambda x: -x[1])[:12]:
    print("    %-34s %d" % (д[:34], k))
