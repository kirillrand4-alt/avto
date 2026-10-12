# -*- coding: utf-8 -*-
"""Снять с писем кампании 14 закрепление за ящиком, оставленное таймаутами.

Делать ПОСЛЕ перезапуска SenderPanel с исправленным mark_failed и НЕ во
время прохода автоотправки (окно 09:00–14:00 МСК): старый код при новом
таймауте прибил бы письма обратно. Трогаем только status='scheduled' —
письма в 'sending' в работе у прохода.

Запуск: snyat_zakreplenie_14.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time

ПРИМЕНИТЬ = "--primenit" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
print("время сервера: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
строки = [dict(р) for р in c.execute(
    "SELECT id, status, mailbox_id, attempt_count, substr(last_error,1,60) e "
    "FROM messages WHERE campaign_id=14 AND status IN ('scheduled','sending') "
    "AND mailbox_id IS NOT NULL ORDER BY id")]
по = {}
for р in строки:
    по.setdefault((р["status"], р["mailbox_id"]), 0)
    по[(р["status"], р["mailbox_id"])] += 1
for (ст, ящ), n in по.items():
    print("   %-9s %-36s %3d" % (ст, ящ, n))
снять = [р["id"] for р in строки if р["status"] == "scheduled"]
if ПРИМЕНИТЬ and снять:
    м = ",".join(str(int(x)) for x in снять)
    c.execute("UPDATE messages SET mailbox_id=NULL WHERE id IN (%s) "
              "AND status='scheduled'" % м)
    c.commit()
    with io.open(r"C:\sender\_ops\snyat-zakreplenie-14.jsonl", "a",
                 encoding="utf-8") as ж:
        ж.write(json.dumps({"ts": int(time.time()), "ids": снять},
                           ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
print("=== ЗАКРЕПЛЕНИЕ: %s, писем %d ==="
      % ("СНЯТО" if ПРИМЕНИТЬ else "сухой прогон", len(снять)))
