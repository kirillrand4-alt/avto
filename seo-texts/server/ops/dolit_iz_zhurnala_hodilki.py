# -*- coding: utf-8 -*-
"""Долить в requisites то, что ходилка добыла, но не смогла записать.

Ходилка пишет результат в ДВА места: в базу и в журнал checko_finansy.jsonl,
причём запись в журнал идёт независимо от того, легла ли запись в базу. Когда
база занята (часовая сверка приговоров, заливка, сама ходилка с её коммитом
раз в сто компаний), обновление в requisites теряется, а строка в журнале
остаётся. Этот оп переносит журнал в базу.

Пишем крупными пачками в отдельном соединении с BEGIN IMMEDIATE: число
захватов замка важнее скорости самой записи.

По умолчанию СУХОЙ ПРОГОН. Запуск: python dolit_iz_zhurnala_hodilki.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

БАЗА = r"C:\sender\enrich.db"
ЖУРНАЛ = r"C:\sender\server\checko_finansy.jsonl"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv
ПОЛЯ = ("revenue_rub", "profit_rub", "ssch", "fin_god", "ssch_god",
        "okved_all_checko", "okved_main_checko", "okved_count",
        "phones_checko", "emails_checko", "site_checko")


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


# журнал: последняя запись по каждому ИНН побеждает
из_журнала = {}
сбоев, строк = 0, 0
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        с = с.strip()
        if not с:
            continue
        строк += 1
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if z.get("сбой"):
            сбоев += 1
            continue
        и = цифры(z.get("inn"))
        if и and any(z.get(к) not in (None, "") for к in ПОЛЯ):
            из_журнала[и] = z

# что уже в базе
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=120)
в_базе = {}
for и, в in c.execute("SELECT inn, revenue_rub FROM requisites"):
    в_базе[цифры(и)] = в
c.close()

нужно = [и for и in из_журнала
         if и in в_базе and str(в_базе[и] or "") in ("", "0")]

записано, повторов, пачек = 0, 0, 0
if ПРИМЕНИТЬ and нужно:
    зп = sqlite3.connect(БАЗА, timeout=180, isolation_level=None)
    зп.execute("PRAGMA busy_timeout = 180000")
    ПАЧКА = 2000
    for н in range(0, len(нужно), ПАЧКА):
        кусок = нужно[н:н + ПАЧКА]
        данные = [[str(из_журнала[и].get(к, "") or "") for к in ПОЛЯ]
                  + [time.strftime("%Y-%m-%dT%H:%M:%S"), и] for и in кусок]
        for попытка in range(120):
            try:
                зп.execute("BEGIN IMMEDIATE")
                зп.executemany(
                    "UPDATE requisites SET "
                    + ", ".join("%s=?" % к for к in ПОЛЯ)
                    + ", updated_at=? WHERE inn=?", данные)
                зп.execute("COMMIT")
                записано += len(кусок)
                пачек += 1
                print("   пачек %d, записано %d из %d"
                      % (пачек, записано, len(нужно)), flush=True)
                break
            except sqlite3.OperationalError as ex:
                if "locked" not in str(ex) and "busy" not in str(ex):
                    raise
                повторов += 1
                try:
                    зп.execute("ROLLBACK")
                except Exception:                              # noqa: BLE001
                    pass
                time.sleep(5.0)
    зп.close()

r = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=120)
с_выручкой = r.execute(
    "SELECT COUNT(*) FROM requisites "
    " WHERE COALESCE(revenue_rub,'') NOT IN ('','0')").fetchone()[0]
от_30 = r.execute(
    "SELECT COUNT(*) FROM requisites "
    " WHERE CAST(COALESCE(revenue_rub,'0') AS INTEGER) >= 30000000"
).fetchone()[0]
r.close()

print("=" * 70)
print("=== СВОДКА: ДОЛИВКА ИЗ ЖУРНАЛА ХОДИЛКИ ===")
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("")
print("строк в журнале: %d (сбоев %d), полезных записей %d"
      % (строк, сбоев, len(из_журнала)))
print("из них в базе без выручки — К ДОЛИВКЕ: %d" % len(нужно))
if ПРИМЕНИТЬ:
    print("записано: %d, пачек %d, повторов из-за замка %d"
          % (записано, пачек, повторов))
print("")
print("requisites сейчас: с выручкой %d, из них от 30 млн %d"
      % (с_выручкой, от_30))
