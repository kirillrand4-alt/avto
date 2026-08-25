# -*- coding: utf-8 -*-
"""Лежат ли тексты потерянных писем в журнале — можно ли их доложить.

Генератор пишет тело письма в журнал ДО того, как отдать его очереди.
Если тела там есть, деньги не сожжены: письма можно разложить по свежим
карточкам, а не писать заново.
"""
import io
import json
import os
import sqlite3
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row

# Берём хвост журнала: там записи сегодняшних блоков.
with io.open(ЖУРНАЛ, "rb") as ф:
    ф.seek(max(0, os.path.getsize(ЖУРНАЛ) - 3000000))
    хвост = ф.read().decode("utf-8", "replace").splitlines()[1:]

с_телом = []
свод = Counter()
for с in хвост:
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if not з.get("ок"):
        continue
    есть_тело = bool(з.get("тело"))
    свод["ок, тело есть" if есть_тело else "ок, тела НЕТ"] += 1
    if есть_тело:
        с_телом.append(з)

print("записей «ок» в хвосте журнала: %d" % sum(свод.values()))
for к, н in свод.most_common():
    print("   %-24s %5d" % (к, н))

# Из них — те, чья карточка снята (письмо невидимо).
потеряны = []
for з in с_телом:
    rid = з.get("review_id")
    if not rid:
        continue
    р = c.execute("SELECT cr.status cs, COALESCE(m.status,'нет') ms "
                  "  FROM confirm_reviews cr "
                  "  LEFT JOIN messages m ON m.id=cr.message_id "
                  " WHERE cr.id=?", (int(rid),)).fetchone()
    if р and (р["cs"] == "skipped" or р["ms"] == "skipped"):
        потеряны.append(з)
print("\nиз них легло в СНЯТЫЕ карточки (невидимы): %d" % len(потеряны))
if потеряны:
    з = потеряны[-1]
    print("\nпример потерянного письма:")
    print("   компания: %s (ИНН %s), карточка #%s"
          % (з.get("имя"), з.get("inn"), з.get("review_id")))
    print("   тема: %s" % str(з.get("тема") or "")[:80])
    print("   тело: %s" % " ".join(str(з.get("тело") or "").split())[:200])

print("\nоп для догрузки из журнала на сервере: %s"
      % ("есть" if os.path.exists(
          r"C:\sender\_ops\partiya_dolozhit_iz_zhurnala.py") else "НЕТ"))
