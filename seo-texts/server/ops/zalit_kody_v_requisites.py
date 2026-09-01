# -*- coding: utf-8 -*-
"""Залить в enrich.db.requisites компании названных кодов из сбора по Чеко.

Владелец 01.09 назвал шесть строк разбивки: выращивание зерновых (01.11 и
01.11.1), оптовая торговля зерном и кормами (46.21), оптовая торговля
прочими пищевыми (46.38), смешанное сельское хозяйство (01.50), молочный
скот (01.41). Кладём ИНН+ОГРН+название+ОКВЭД, чтобы ходилка checko_finansy
увидела их и добрала выручку.

Совпадение кода ТОЧНОЕ, а не по началу строки: у 01.11 в сборе есть ещё
01.11.2, 01.11.3, 01.11.31, у 46.21 — 46.21.1, 46.21.11 и другие. Их
владелец не называл, поэтому считаем отдельно и НЕ кладём — цифру покажем,
чтобы решение было при данных.

Чужие строки не трогаем вовсе: INSERT OR IGNORE по первичному ключу inn.
По умолчанию СУХОЙ ПРОГОН. Запуск: python zalit_kody_v_requisites.py [--primenit]
"""
import csv
import io
import os
import sqlite3
import sys
import time
from collections import Counter

CSV = r"C:\seostat\Parser2\data\agro-base.csv"
БАЗА = r"C:\sender\enrich.db"
ЖУРНАЛ = r"C:\sender\_ops\zaliv-requisites.jsonl"
ПРИМЕНИТЬ = "--primenit" in sys.argv or "--apply" in sys.argv

КОДЫ = {
    "01.11": "выращивание зерновых",
    "01.11.1": "выращивание зерновых",
    "46.21": "оптовая торговля зерном и кормами",
    "46.38": "оптовая торговля прочими пищевыми",
    "01.50": "смешанное сельское хозяйство",
    "01.41": "молочный скот",
}
СЕМЬИ = sorted({к.split(".")[0] + "." + к.split(".")[1] for к in КОДЫ})


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


берём, семьи_лишние = [], Counter()
по_кодам = Counter()
без_огрн = 0
with io.open(CSV, encoding="utf-8-sig", errors="replace", newline="") as ф:
    for р in csv.DictReader(ф, delimiter=";"):
        код = str(р.get("Основной ОКВЭД") or "").strip()
        инн = цифры(р.get("ИНН"))
        огрн = цифры(р.get("ОГРН"))
        if код in КОДЫ:
            по_кодам[код] += 1
            if not инн or not огрн:
                без_огрн += 1
                continue
            берём.append((инн, огрн,
                          str(р.get("Название") or "").strip()[:200],
                          str(р.get("Полное название") or "").strip()[:300],
                          код,
                          str(р.get("Адрес") or "").strip()[:300],
                          str(р.get("Статус") or "").strip()[:40]))
        else:
            # подкоды тех же семей — считаем, но не берём
            for с in СЕМЬИ:
                if код.startswith(с + ".") or код == с:
                    семьи_лишние[код] += 1
                    break

# что из этого уже есть в requisites
c = sqlite3.connect(БАЗА, timeout=180)
есть = {цифры(r[0]) for r in c.execute("SELECT inn FROM requisites")}
новых = [р for р in берём if р[0] not in есть]
уже = len(берём) - len(новых)

вставлено = 0
пачек, повторов, не_легло = 0, 0, 0
if ПРИМЕНИТЬ and новых:
    метка = time.strftime("%Y-%m-%dT%H:%M:%S")
    # БАЗА ЗАНЯТА — ЭТО НОРМА, А НЕ АВАРИЯ. enrich.db читают генерация и
    # обогатители, и одна транзакция на 35 тысяч строк не получит замок
    # никогда: 01.09 первый заход упал с «database is locked». Пишем
    # КОРОТКИМИ пачками, каждая своей транзакцией, с повторами. INSERT OR
    # IGNORE делает прогон идемпотентным, поэтому повтор ничего не портит
    # и упавшую заливку можно просто запустить заново.
    c.execute("PRAGMA busy_timeout = 60000")
    ПАЧКА = 500
    for н in range(0, len(новых), ПАЧКА):
        кусок = новых[н:н + ПАЧКА]
        for попытка in range(8):
            try:
                c.executemany(
                    "INSERT OR IGNORE INTO requisites "
                    "  (inn, ogrn, name_short, name_full, okved_main, "
                    "   address, status, src, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,'checko-sbor-agro',?)",
                    [(и, о, нк, нп, к, а, с, метка)
                     for и, о, нк, нп, к, а, с in кусок])
                c.commit()
                пачек += 1
                break
            except sqlite3.OperationalError as ex:
                if "locked" not in str(ex) and "busy" not in str(ex):
                    raise
                повторов += 1
                try:
                    c.rollback()
                except Exception:                              # noqa: BLE001
                    pass
                time.sleep(min(20.0, 1.5 * (попытка + 1)))
        else:
            не_легло += len(кусок)
    вставлено = c.execute(
        "SELECT COUNT(*) FROM requisites WHERE src='checko-sbor-agro'"
    ).fetchone()[0]
    # durability: журнал рядом с базой, с fsync
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
        ж.write('{"когда":"%s","кодов":%d,"вставлено_всего_меткой":%d,'
                '"новых_в_этом_прогоне":%d}\n'
                % (метка, len(КОДЫ), вставлено, len(новых)))
        ж.flush()
        os.fsync(ж.fileno())
итого_рек = c.execute("SELECT COUNT(*) FROM requisites").fetchone()[0]
с_огрн = c.execute(
    "SELECT COUNT(*) FROM requisites WHERE COALESCE(ogrn,'')<>''").fetchone()[0]
c.close()

print("=" * 68)
print("=== СВОДКА: ЗАЛИВКА НАЗВАННЫХ КОДОВ ===")
print("режим: %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "СУХОЙ ПРОГОН"))
print("")
print("НАЗВАННЫЕ КОДЫ (точное совпадение):")
всего = 0
for к in ("01.11", "01.11.1", "46.21", "46.38", "01.50", "01.41"):
    н = по_кодам.get(к, 0)
    всего += н
    print("   %-9s %7d   %s" % (к, н, КОДЫ[к]))
print("   %-9s %7d   ВСЕГО" % ("", всего))
print("")
print("   без ИНН или ОГРН (не берём):     %6d" % без_огрн)
print("   уже есть в requisites:           %6d" % уже)
print("   К ЗАЛИВКЕ НОВЫХ:                 %6d" % len(новых))
if ПРИМЕНИТЬ:
    print("   строк с меткой checko-sbor-agro: %6d" % вставлено)
    print("   пачек записано: %d, повторов из-за замка: %d, не легло: %d"
          % (пачек, повторов, не_легло))
print("")
print("ПОДКОДЫ ТЕХ ЖЕ СЕМЕЙ, которые НЕ названы и НЕ залиты:")
for к, н in семьи_лишние.most_common(12):
    print("   %-10s %6d" % (к, н))
print("   итого подкодов: %d компаний" % sum(семьи_лишние.values()))
print("")
print("таблица requisites теперь: %d строк, с ОГРН %d" % (итого_рек, с_огрн))
