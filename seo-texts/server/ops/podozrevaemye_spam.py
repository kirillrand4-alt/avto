# -*- coding: utf-8 -*-
"""Подозреваемые: чьи письма вероятнее падают в спам.

Владелец проверил живьём — письмо с optic-sort.ru упало у Gmail в спам.
Считаем по каждому домену и ящику то, что видно из базы, и складываем в
один список подозрений.

Сигналы:
  * ОТКЛИК. Письма доходят, но никто не отвечает — первый признак папки
    «Спам»: отбивки нет, реакции нет;
  * ОТБИВКИ. Много отбивок = плохие адреса, они же роняют репутацию домена;
  * ВОЗРАСТ ДОМЕНА. Свежий домен с холодной рассылкой — классический повод
    для фильтра;
  * ПОЧТОВИК. Mail.ru и Яндекс по-разному видятся у Gmail.
"""
import json
import re
import socket
import sqlite3
import ssl
import subprocess
import urllib.request
from collections import defaultdict

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

отпр = defaultdict(int)
for r in c.execute("SELECT mailbox_id, COUNT(*) n FROM messages "
                   " WHERE sent_at IS NOT NULL GROUP BY mailbox_id"):
    отпр[str(r["mailbox_id"] or "")] = r["n"]
вход = defaultdict(lambda: defaultdict(int))
for r in c.execute("SELECT mailbox_id, event_type, COUNT(*) n FROM events "
                   " WHERE event_type IN ('reply','reply_auto','bounce','open') "
                   " GROUP BY mailbox_id, event_type"):
    вход[str(r["mailbox_id"] or "")][r["event_type"]] = r["n"]

домены = defaultdict(lambda: {"ушло": 0, "жив": 0, "авто": 0, "отб": 0,
                              "ящиков": 0, "нулевых": []})
for я, о in отпр.items():
    if "@" not in я:
        continue
    д = я.rsplit("@", 1)[-1]
    в = вход[я]
    домены[д]["ушло"] += о
    домены[д]["жив"] += в.get("reply", 0)
    домены[д]["авто"] += в.get("reply_auto", 0)
    домены[д]["отб"] += в.get("bounce", 0)
    домены[д]["ящиков"] += 1
    if в.get("reply", 0) == 0 and о >= 50:
        домены[д]["нулевых"].append("%s (%d писем)" % (я.split("@")[0], о))


def spf_почтовик(д):
    try:
        out = subprocess.run(["nslookup", "-type=TXT", д, "8.8.8.8"],
                             capture_output=True, text=True, timeout=20)
        т = (out.stdout or "").lower()
        if "_spf.mail.ru" in т:
            return "mail.ru"
        if "_spf.yandex" in т:
            return "yandex"
    except Exception:                                         # noqa: BLE001
        pass
    return "?"


print("%-28s %6s %6s %6s %6s %7s %7s  %-8s"
      % ("домен", "ящиков", "ушло", "живых", "отбив", "живых%", "отбив%",
         "почтовик"))
строки = []
for д, з in sorted(домены.items(), key=lambda x: -x[1]["ушло"]):
    о = з["ушло"] or 1
    жп = 100.0 * з["жив"] / о
    оп = 100.0 * з["отб"] / о
    п = spf_почтовик(д)
    строки.append((д, з, жп, оп, п))
    print("%-28s %6d %6d %6d %6d %6.1f%% %6.1f%%  %-8s"
          % (д[:28], з["ящиков"], з["ушло"], з["жив"], з["отб"], жп, оп, п))

print("")
print("=== ПОДОЗРЕВАЕМЫЕ (по отклику) ===")
средний = (100.0 * sum(з["жив"] for _д, з, _ж, _о, _п in строки)
           / max(1, sum(з["ушло"] for _д, з, _ж, _о, _п in строки)))
print("средний живой отклик: %.1f%%" % средний)
for д, з, жп, оп, п in sorted(строки, key=lambda x: x[2]):
    if з["ушло"] < 50:
        continue
    if жп < средний * 0.75:
        print("   %-28s %5.1f%% против %.1f%% среднего | ушло %d | почтовик %s"
              % (д[:28], жп, средний, з["ушло"], п))
        for н in з["нулевых"]:
            print("        ящик без единого живого ответа: %s" % н)
c.close()
