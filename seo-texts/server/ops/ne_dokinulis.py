# -*- coding: utf-8 -*-
"""Есть ли письма, которые сгенерированы, но в очередь не попали.

Владелец: «так и не докинулись в очередь». Проверяем не счётчики виджета,
а сам факт: в журнале есть письма с телом и без review_id — за них
заплачено, а в очереди их нет. Их докладывает partiya_dolozhit_iz_zhurnala.
"""
import io
import json
import os
import sqlite3
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

вочереди = c.execute("SELECT COUNT(*) n FROM confirm_reviews "
                     " WHERE status='pending'").fetchone()["n"]
всего = c.execute("SELECT COUNT(*) n FROM confirm_reviews").fetchone()["n"]
print("в базе pending: %d (всех карточек %d)" % (вочереди, всего))

итог = {}
for с in io.open(ЖУРНАЛ, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("этап") != "итог":
        continue
    inn = str(з.get("inn") or "")
    if inn:
        итог[inn] = з

с_телом = [з for з in итог.values() if з.get("тело")]
без_очереди = [з for з in с_телом if not з.get("review_id")]
print("\n=== ПО ЖУРНАЛУ (последняя запись «итог» на компанию) ===")
print("  компаний с готовым письмом: %d" % len(с_телом))
print("  из них БЕЗ review_id (в очередь не попали): %d" % len(без_очереди))

# сверяем с базой: может, карточка есть, а в журнале id не записался
реально_нет = []
for з in без_очереди:
    rid = з.get("recipient_id")
    есть = c.execute("SELECT COUNT(*) n FROM confirm_reviews "
                     " WHERE recipient_id=?", (rid,)).fetchone()["n"] if rid else 0
    if not есть:
        реально_нет.append(з)
print("  из них в базе карточки НЕТ вовсе: %d" % len(реально_нет))

if реально_нет:
    print("\n  первые десять:")
    for з in реально_нет[:10]:
        print("    %-38s %s | %s"
              % (str(з.get("имя"))[:38], з.get("направление"),
                 str(з.get("тема"))[:44]))
    прич = Counter(str((з.get("брак") or ["-"])[0])[:50] for з in реально_нет)
    print("\n  что записано в «брак» у этих:")
    for к, н in прич.most_common(8):
        print("    %-52s %d" % (к, н))

print("\n=== СТАТУСЫ ОЧЕРЕДИ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT status, COUNT(*) n FROM confirm_reviews "
        " WHERE substr(created_at,1,10)=date('now') GROUP BY status ORDER BY n DESC"):
    print("  %-14s %5d" % (р["status"], р["n"]))

print("\n=== ЧТО УСПЕЛ БЛОК 2 ДО ОСТАНОВКИ ===")
п = r"C:\sender\_ops\ochered-blok2-kc.log"
if os.path.exists(п):
    строки = io.open(п, encoding="utf-8", errors="replace").readlines()
    print("  строк в логе: %d, обновлён %.1f мин назад"
          % (len(строки), (time.time() - os.path.getmtime(п)) / 60.0))
    писем = [с for с in строки if "] ОК " in с or "] брак" in с]
    print("  писем в логе: %d" % len(писем))
    for с in писем[-6:]:
        print("    %s" % с.rstrip()[:150])
else:
    print("  лога блока 2 нет")
