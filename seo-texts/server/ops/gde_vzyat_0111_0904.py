# -*- coding: utf-8 -*-
"""Только чтение: есть ли где-нибудь компании с ОКВЭД 01.11."""
import sqlite3

o = sqlite3.connect("file:C:/sender/obzvon-index.db?mode=ro", uri=True)
o.row_factory = sqlite3.Row
e = sqlite3.connect("file:C:/sender/enrich.db?mode=ro", uri=True)
e.row_factory = sqlite3.Row

print("=== ИНДЕКС ОБЗВОНА ===")
print("  всего строк: %d" % o.execute("SELECT COUNT(*) FROM obzvon").fetchone()[0])
for поле in ("okved_main", "okved_all_codes", "equip_by_okved"):
    try:
        n = o.execute("SELECT COUNT(*) FROM obzvon WHERE %s LIKE '01.11%%'"
                      % поле).fetchone()[0]
        print("  %s начинается с 01.11: %d" % (поле, n))
    except Exception as ex:
        print("  %s: %s" % (поле, str(ex)[:60]))
n = o.execute("SELECT COUNT(*) FROM obzvon WHERE okved_all_codes LIKE '%01.11%'"
              ).fetchone()[0]
print("  01.11 где-либо в okved_all_codes: %d" % n)
print("\n  топ okved_main в индексе:")
for р in o.execute("SELECT substr(okved_main,1,5) к, COUNT(*) n FROM obzvon"
                   " GROUP BY к ORDER BY n DESC LIMIT 10"):
    print("    %-8s %d" % (р["к"], р["n"]))
print("\n  сельскохозяйственные коды 01.x в индексе:")
for р in o.execute("SELECT substr(okved_main,1,5) к, COUNT(*) n FROM obzvon"
                   " WHERE okved_main LIKE '01.%' GROUP BY к ORDER BY n DESC LIMIT 12"):
    print("    %-8s %d" % (р["к"], р["n"]))

print("\n=== ДРУГИЕ ТАБЛИЦЫ ОБОГАЩЕНИЯ ===")
for т in ("base_ref", "vne_bazy", "eis_arch", "donors", "requisites", "signals"):
    try:
        кол = [r["name"] for r in e.execute("PRAGMA table_info(%s)" % т)]
        n = e.execute("SELECT COUNT(*) FROM %s" % т).fetchone()[0]
        окв = [k for k in кол if "okved" in k.lower()]
        доп = ""
        if окв:
            k = e.execute("SELECT COUNT(*) FROM %s WHERE %s LIKE '01.11%%'"
                          % (т, окв[0])).fetchone()[0]
            доп = " | 01.11: %d" % k
        print("  %-12s %7d строк | поля ОКВЭД: %s%s" % (т, n, окв, доп))
    except Exception as ex:
        print("  %-12s %s" % (т, str(ex)[:60]))
