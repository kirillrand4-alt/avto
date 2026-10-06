# -*- coding: utf-8 -*-
"""Потолок: сколько компаний в базе ВООБЩЕ имеют подтверждённый сайт с описанием.

813 — это сколько компаний получили письмо, в карточке которого на момент
отправки стояло описание с подтверждённого сайта. Это не потолок: карточка
— снимок на момент отправки, а обогащение с тех пор шло дальше, и часть
базы вообще не написана.

Подтверждение сайта (company_card._SITE_VERIFIED_OK): verified из
{inn, ogrn, phone, provider}.
"""
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ОК = ("inn", "ogrn", "phone", "provider")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

путь = r"C:\sender\enrich.db"
if not os.path.exists(путь):
    raise SystemExit("нет %s" % путь)
cx = sqlite3.connect("file:%s?mode=ro" % путь, uri=True)
cx.row_factory = sqlite3.Row

кол = [x[1] for x in cx.execute("PRAGMA table_info(companies)")]
print("--- колонки companies: %s" % ", ".join(кол))
всего = cx.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
print("компаний в обогащении: %d" % всего)

print("")
print("--- по значению verified ---")
for р in cx.execute("SELECT COALESCE(verified,'(пусто)') v, COUNT(*) n "
                    "  FROM companies GROUP BY 1 ORDER BY 2 DESC LIMIT 10"):
    метка = "  ← считается подтверждённым" if р["v"] in ОК else ""
    print("   %-14s %6d%s" % (р["v"], р["n"], метка))

плейс = ",".join("?" * len(ОК))
сверен = cx.execute(
    "SELECT COUNT(*) FROM companies WHERE verified IN (%s) "
    "  AND COALESCE(site,'')<>''" % плейс, ОК).fetchone()[0]
с_опис = cx.execute(
    "SELECT COUNT(*) FROM companies WHERE verified IN (%s) "
    "  AND COALESCE(site,'')<>'' AND COALESCE(activity,'')<>''" % плейс,
    ОК).fetchone()[0]
print("")
print("--- потолок по обогащению ---")
print("   сайт подтверждён:                 %6d" % сверен)
print("   он же + описание деятельности:    %6d" % с_опис)

# кому из них уже писали с ящиков Meyer
МЕЙЕР = ("optic-sort.ru", "sort-systems.ru", "zernosort.ru", "food-sort.ru",
         "sorting-systems.ru", "rentgen-control.ru", "optical-sort.ru",
         "rentgen-inspection.ru", "inspection-systems.ru")
усл = " OR ".join("m.mailbox_id LIKE '%%%s'" % д for д in МЕЙЕР)
писали = set()
with store._lock:
    for р in store._conn.execute(
            "SELECT DISTINCT r.inn FROM messages m "
            "  JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND (%s)" % усл):
        if р["inn"]:
            писали.add(str(р["inn"]).strip())

годные = set()
for р in cx.execute(
        "SELECT inn FROM companies WHERE verified IN (%s) "
        "  AND COALESCE(site,'')<>'' AND COALESCE(activity,'')<>''" % плейс, ОК):
    если = str(р["inn"] or "").strip()
    if если:
        годные.add(если)
cx.close()

пересечение = годные & писали
print("")
print("=" * 74)
print("=== ПОТОЛОК ПАСПОРТА С САЙТА ===")
print("   компаний в обогащении всего:            %6d" % всего)
print("   с подтверждённым сайтом и описанием:    %6d" % len(годные))
print("   из них Meyer уже писал:                 %6d" % len(пересечение))
print("   из них ещё НЕ писали:                   %6d"
      % (len(годные) - len(пересечение)))
