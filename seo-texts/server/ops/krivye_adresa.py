# -*- coding: utf-8 -*-
"""nfo@ и yh@ — это обрезанные info@ и что-то ещё? Смотрим, откуда взялись."""
import json
import sqlite3
БАЗА = r"C:\sender\sender.db"
ОБОГ = r"C:\sender\enrich.db"
ПОДОЗРИТЕЛЬНЫЕ = ("nfo@bstdom.ru", "yh@gk-znk.ru", "cpo@uralkali.com",
                  "rop@morpro.ru", "dse@sdexport.ru", "spb@aldox.ru",
                  "al@vebfabrika.ru")
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
for адрес in ПОДОЗРИТЕЛЬНЫЕ:
    домен = адрес.split("@")[-1]
    соседи = [r["email"] for r in c.execute(
        "SELECT email FROM recipients WHERE email LIKE ?", ("%@" + домен,))]
    print("%-24s соседи по домену: %s" % (адрес, ", ".join(соседи[:6]) or "—"))
c.close()
print()
try:
    e = sqlite3.connect("file:%s?mode=ro" % ОБОГ, uri=True, timeout=60)
    e.row_factory = sqlite3.Row
    for адрес in ПОДОЗРИТЕЛЬНЫЕ:
        строки = list(e.execute(
            "SELECT email, source, source_url FROM emails WHERE LOWER(email)=?",
            (адрес,)))
        for s in строки:
            print("%-24s источник=%s %s" % (s["email"], s["source"],
                                            str(s["source_url"] or "")[:70]))
        домен = адрес.split("@")[-1]
        рядом = [r["email"] for r in e.execute(
            "SELECT DISTINCT email FROM emails WHERE email LIKE ?",
            ("%@" + домен,))]
        print("     в обогащении по домену: %s" % (", ".join(рядом[:8]) or "—"))
    e.close()
except Exception as ex:
    print("enrich.db: %s" % ex)
