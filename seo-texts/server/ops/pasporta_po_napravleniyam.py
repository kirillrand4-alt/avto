# -*- coding: utf-8 -*-
"""Паспорта по направлениям: сколько из них вообще для Meyer.

В enrich.db лежит ВСЯ база, обе ветки. Компрессорные компании Meyer не
писал бы никогда, и считать их «неиспользованными паспортами Meyer» —
ошибка. Разбираем 8 404 по division, конкурентам и факту отправки.
"""
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ОК = ("inn", "ogrn", "phone", "provider")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cx = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True)
cx.row_factory = sqlite3.Row
плейс = ",".join("?" * len(ОК))
УСЛ = ("verified IN (%s) AND COALESCE(site,'')<>'' "
       "  AND COALESCE(activity,'')<>''" % плейс)

print("--- паспорта по направлению (division в обогащении) ---")
for р in cx.execute("SELECT COALESCE(NULLIF(division,''),'(пусто)') d, "
                    "       COUNT(*) n FROM companies WHERE %s "
                    " GROUP BY 1 ORDER BY 2 DESC" % УСЛ, ОК):
    print("   %-14s %6d" % (р["d"], р["n"]))

print("")
print("--- из них конкуренты ---")
р = cx.execute("SELECT SUM(CASE WHEN is_competitor IN (1,'1','да','true') "
               "  THEN 1 ELSE 0 END) k, COUNT(*) n FROM companies WHERE %s"
               % УСЛ, ОК).fetchone()
print("   конкурентов: %s из %s" % (р["k"], р["n"]))

# кому писали с ящиков Meyer
МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
усл_м = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
писали, в_базе_писем = set(), set()
with store._lock:
    for р in store._conn.execute(
            "SELECT DISTINCT r.inn FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND (%s)" % усл_м):
        if р["inn"]:
            писали.add(str(р["inn"]).strip())
    # и кто вообще заведён получателем (не только отправленные)
    for р in store._conn.execute("SELECT DISTINCT inn FROM recipients "
                                 " WHERE COALESCE(inn,'')<>''"):
        в_базе_писем.add(str(р["inn"]).strip())

итог = {}
for р in cx.execute("SELECT inn, COALESCE(NULLIF(division,''),'(пусто)') d, "
                    "       is_competitor FROM companies WHERE %s" % УСЛ, ОК):
    и = str(р["inn"] or "").strip()
    if not и:
        continue
    итог[и] = (р["d"], str(р["is_competitor"] or ""))
cx.close()

мейер = {и for и, (d, k) in итог.items()
         if d == "meyer" and k not in ("1", "да", "true")}
print("")
print("=" * 74)
print("=== ПАСПОРТА, ПРИГОДНЫЕ ДЛЯ MEYER ===")
print("   паспортов всего в базе:            %6d" % len(итог))
print("   из них направление meyer:          %6d" % len(мейер))
print("      им уже писали с ящиков Meyer:   %6d" % len(мейер & писали))
print("      заведены получателем, но письма нет: %4d"
      % len((мейер & в_базе_писем) - писали))
print("      вообще не заводились:           %6d"
      % len(мейер - в_базе_писем))
