# -*- coding: utf-8 -*-
"""Только чтение: жив ли цикл автоотправки. Спрашиваем у самой панели."""
import datetime as dt
import inspect
import io
import json
import os
import re
import sqlite3
import sys
import urllib.request

sys.path.insert(0, r"C:\sender")

print("=== ЧТО ОТДАЁТ ЭНДПОИНТ auto_send ===")
т = io.open(r"C:\sender\sender\api\app.py", encoding="utf-8", errors="replace").read()
лн = т.splitlines()
н = next(i for i, л in enumerate(лн) if "def auto_send_get" in л)
for i in range(max(0, н - 3), min(len(лн), н + 20)):
    print("  %5d| %s" % (i + 1, лн[i][:104]))

print("\n=== СПРАШИВАЕМ ПАНЕЛЬ ===")
for путь in ("/api/auto-send", "/api/auto_send", "/api/autosend"):
    try:
        зпр = urllib.request.Request("http://127.0.0.1:8091" + путь)
        with urllib.request.urlopen(зпр, timeout=15) as r:
            print("  %s -> %s" % (путь, r.read().decode("utf-8", "replace")[:400]))
            break
    except Exception as ex:
        print("  %s -> %s" % (путь, str(ex)[:90]))

print("\n=== ЗАВИСШИЕ В 'sending': сколько висят ===")
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
for р in c.execute("SELECT id, claimed_at, updated_at FROM messages WHERE status='sending'"):
    try:
        взято = dt.datetime.fromisoformat(р["claimed_at"])
        часов = (сейчас - взято).total_seconds() / 3600.0
    except Exception:
        часов = -1
    print("  msg#%s взято %s — висит %.1f ч" % (р["id"], р["claimed_at"], часов))
print("  (аренда lease_ttl_sec=900, то есть 15 минут: живой цикл вернул бы их давно)")

print("\n=== ГДЕ СЛУЖБА ПИШЕТ ВЫВОД ===")
свежие = []
for корень in (r"C:\sender", r"C:\sender\logs", r"C:\sender\var", r"C:\sender\run"):
    if not os.path.isdir(корень):
        continue
    for имя in os.listdir(корень):
        п = os.path.join(корень, имя)
        if os.path.isfile(п):
            м = dt.datetime.fromtimestamp(os.path.getmtime(п))
            if (сейчас - м).total_seconds() < 86400 * 2:
                свежие.append((м, os.path.relpath(п, r"C:\sender"),
                               os.path.getsize(п)))
for м, п, р2 in sorted(свежие, reverse=True)[:12]:
    print("  %s  %10d Б  %s" % (м.strftime("%m-%d %H:%M"), р2, п))
