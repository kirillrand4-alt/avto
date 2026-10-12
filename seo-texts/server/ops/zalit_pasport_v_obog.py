# -*- coding: utf-8 -*-
"""Залить паспорт top100 в обогащение: компании и адреса.

Ключи: российский ИНН как есть, белорусский УНП цифрами (9 знаков),
у кого номера нет — служебный «00000000001» в одиннадцать знаков. Ни с
российским (10/12), ни с белорусским (9) не спутаешь, и глазом видно,
что это не ИНН. Метка вида ключа идёт в istochnik_kompanii.

Что НЕ перетираем: уже заполненные site, verified, revenue, okved,
division. Паспорт кладём в activity — это знание о компании, а не повод,
и в signals ему не место: оттуда письмо начало бы с него как с события.

Сайт считаем сверенным только там, где номер компании найден НА СТРАНИЦЕ
и проверяющий подтвердил — 31 из 100.

argv: --primenit чтобы записать.
"""
import io
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

БАЗА = r"C:\sender\enrich.db"
ФАЙЛ = r"C:\sender\server\ops\obog_top100.json"
ПРИМЕНИТЬ = "--primenit" in sys.argv
МЕТКА = "паспорт MEYER-7 top100, 12.10"

д = json.load(io.open(ФАЙЛ, encoding="utf-8"))
компании, адреса = д["компании"], д["адреса"]
ключи = [к["inn"] for к in компании]
print("в файле: компаний %d, адресов %d" % (len(компании), len(адреса)))

cx = sqlite3.connect(БАЗА, timeout=60)
cx.row_factory = sqlite3.Row
cx.execute("PRAGMA busy_timeout=60000")
метки = ",".join("?" * len(ключи))
было_к = {р["inn"]: dict(р) for р in cx.execute(
    "SELECT * FROM companies WHERE inn IN (%s)" % метки, ключи)}
было_а = {(р["inn"], р["email"]): dict(р) for р in cx.execute(
    "SELECT * FROM emails WHERE inn IN (%s)" % метки, ключи)}
print("уже есть в обогащении: компаний %d, адресов %d"
      % (len(было_к), len(было_а)))
новых_к = sum(1 for к in ключи if к not in было_к)
новых_а = sum(1 for а in адреса if (а["inn"], а["email"]) not in было_а)
print("добавится: компаний %d, адресов %d" % (новых_к, новых_а))
print("обновится описанием: %d" % len(компании))
print("сайт пометим сверенным: %d"
      % sum(1 for к in компании if к.get("verified")))

if not ПРИМЕНИТЬ:
    cx.close()
    print("")
    print("=" * 74)
    print("=== ПОКАЗ БЕЗ ЗАПИСИ (нужен --primenit) ===")
    raise SystemExit(0)

# бэкап затрагиваемых строк
папка = r"C:\sender\_ops"
os.makedirs(папка, exist_ok=True)
бэкап = os.path.join(папка, "obog-top100-do-%d.jsonl" % int(time.time()))
with io.open(бэкап, "w", encoding="utf-8") as f:
    for р in было_к.values():
        f.write(json.dumps({"таблица": "companies", **р}, ensure_ascii=False) + "\n")
    for р in было_а.values():
        f.write(json.dumps({"таблица": "emails", **р}, ensure_ascii=False) + "\n")
    f.flush()
    os.fsync(f.fileno())
print("")
print("бэкап прежних строк: %s (%d)" % (бэкап, len(было_к) + len(было_а)))

сейчас = datetime.now(timezone.utc).isoformat(timespec="seconds")
вид_метки = {"инн": "", "унп": "; ключ — УНП цифрами",
             "служебный": "; ключ служебный, номера у компании нет"}
обн_к = вст_к = обн_а = вст_а = 0
for к in компании:
    стар = было_к.get(к["inn"]) or {}
    поля = {
        "name": к["name"] or стар.get("name"),
        "activity": к["activity"] or стар.get("activity"),
        "site": стар.get("site") or к["site"],
        "verified": стар.get("verified") or к.get("verified") or "",
        "region": стар.get("region") or к["region"],
        "okved": стар.get("okved") or к["okved"],
        "okved_all": стар.get("okved_all") or к["okved_all"],
        "revenue_rub": стар.get("revenue_rub") or к["revenue"],
        "division": стар.get("division") or "meyer",
        "istochnik_kompanii": МЕТКА + вид_метки.get(к["vid"], ""),
        "updated_at": сейчас,
    }
    if стар:
        cx.execute("UPDATE companies SET %s WHERE inn=?"
                   % ", ".join("%s=?" % x for x in поля),
                   list(поля.values()) + [к["inn"]])
        обн_к += 1
    else:
        cx.execute("INSERT INTO companies (inn, %s) VALUES (?%s)"
                   % (", ".join(поля), ", ?" * len(поля)),
                   [к["inn"]] + list(поля.values()))
        вст_к += 1

for а in адреса:
    стар = было_а.get((а["inn"], а["email"])) or {}
    if стар:
        cx.execute("UPDATE emails SET role=?, person=?, source_url=?, "
                   "  updated_at=? WHERE inn=? AND email=?",
                   (стар.get("role") or а["role"],
                    стар.get("person") or а["person"],
                    стар.get("source_url") or а["source_url"], сейчас,
                    а["inn"], а["email"]))
        обн_а += 1
    else:
        cx.execute("INSERT INTO emails (inn, email, role, person, source, "
                   "  source_url, updated_at) VALUES (?,?,?,?,?,?,?)",
                   (а["inn"], а["email"], а["role"], а["person"],
                    "паспорт MEYER-7", а["source_url"], сейчас))
        вст_а += 1
cx.commit()

всего = cx.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
адр = cx.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
cx.close()
print("")
print("=" * 74)
print("=== ПАСПОРТ TOP100 В ОБОГАЩЕНИИ ===")
print("   компаний: вставлено %d, обновлено %d" % (вст_к, обн_к))
print("   адресов:  вставлено %d, обновлено %d" % (вст_а, обн_а))
print("   в базе стало: компаний %d, адресов %d" % (всего, адр))
print("   бэкап: %s" % бэкап)
