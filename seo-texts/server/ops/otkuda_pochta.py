# -*- coding: utf-8 -*-
"""Первоисточник адреса marushkiiin@yandex.ru: откуда он у нас."""
import json
import sqlite3

ПОЧТА = "marushkiiin@yandex.ru"


def показать(база, имя):
    print("")
    print("=" * 78)
    print("### %s" % имя)
    try:
        c = sqlite3.connect("file:%s?mode=ro" % база, uri=True, timeout=120)
    except Exception as ex:                                    # noqa: BLE001
        print("   не открылась: %s" % str(ex)[:80])
        return
    c.row_factory = sqlite3.Row
    табл = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    for т in табл:
        try:
            поля = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        except Exception:                                      # noqa: BLE001
            continue
        текстовые = [п for п in поля]
        условия = " OR ".join("CAST(%s AS TEXT) LIKE ?" % п for п in текстовые)
        if not условия:
            continue
        try:
            ряды = c.execute(
                "SELECT * FROM %s WHERE %s LIMIT 4" % (т, условия),
                tuple(["%%%s%%" % ПОЧТА] * len(текстовые))).fetchall()
        except Exception:                                      # noqa: BLE001
            continue
        for r in ряды:
            d = {к: str(r[к])[:200] for к in r.keys() if r[к] not in (None, "")}
            print("")
            print("   --- %s ---" % т)
            for к, v in d.items():
                print("      %-22s %s" % (к, v))
    c.close()


for база, имя in ((r"C:\sender\enrich.db", "enrich.db — обогащение"),
                  (r"C:\sender\sender.db", "sender.db — панель"),
                  (r"C:\sender\obzvon-index.db", "obzvon-index.db — обзвон")):
    показать(база, имя)
