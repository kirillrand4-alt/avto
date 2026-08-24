# -*- coding: utf-8 -*-
"""Чем закончились прогоны генерации и читается ли кэш.

Живых процессов нет, журнал стоит 46 минут. Надо понять: партия дошла до
конца, упёрлась в потолок цены или сорвалась. И отдельно — есть ли в
записях следы чтения кэша промпта.
"""
import glob
import io
import json
import os
import time
from collections import Counter

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
записи = []
for с in io.open(ЖУРНАЛ, encoding="utf-8"):
    с = с.strip()
    if с:
        try:
            записи.append(json.loads(с))
        except Exception:  # noqa: BLE001
            pass
print("записей в журнале: %d" % len(записи))
print("ключи последней: %s" % ", ".join(sorted(записи[-1].keys())))

print("\n=== ПОСЛЕДНИЕ 6 ЗАПИСЕЙ ЦЕЛИКОМ ===")
for з in записи[-6:]:
    print("  " + json.dumps(з, ensure_ascii=False)[:400])

print("\n=== ХВОСТЫ ВЫВОДА ПРОГОНОВ ===")
for п in sorted(glob.glob(r"C:\sender\_ops\*.out")
                + glob.glob(r"C:\sender\_ops\*.log"),
                key=lambda x: -os.path.getmtime(x))[:6]:
    возраст = (time.time() - os.path.getmtime(п)) / 60.0
    if возраст > 400:
        continue
    print("\n  --- %s (обновлён %.1f мин назад, %.0f КБ) ---"
          % (os.path.basename(п), возраст, os.path.getsize(п) / 1024.0))
    try:
        строки = io.open(п, encoding="utf-8", errors="replace").readlines()
    except Exception as e:  # noqa: BLE001
        print("    не прочитан: %s" % e)
        continue
    for с in строки[-16:]:
        print("    %s" % с.rstrip()[:190])

print("\n=== КЭШ: ЧТО ПИШУТ ЗАПИСИ ===")
ключи = Counter()
for з in записи[-400:]:
    for к in з:
        if "кэш" in к.lower() or "cache" in к.lower():
            ключи[к] += 1
print("  ключи про кэш в последних 400 записях: %s"
      % (dict(ключи) or "НЕТ НИ ОДНОГО"))
свежие = [з for з in записи if з.get("цена_$") is not None][-12:]
for з in свежие:
    print("  %s | вызовов %s | цена $%.4f | %s"
          % (str(з.get("имя") or "")[:32], з.get("вызовов"),
             float(з.get("цена_$") or 0),
             ", ".join("%s=%s" % (к, з[к]) for к in з if "кэш" in к.lower())
             or "кэш не отмечен"))

п2 = r"C:\sender\_ops\gen-partiya-935-vyzovy.jsonl"
if os.path.exists(п2):
    выз = []
    for с in io.open(п2, encoding="utf-8"):
        с = с.strip()
        if с:
            try:
                выз.append(json.loads(с))
            except Exception:  # noqa: BLE001
                pass
    print("\n  по-вызовный журнал: %d записей, обновлён %.0f мин назад"
          % (len(выз), (time.time() - os.path.getmtime(п2)) / 60.0))
    if выз:
        print("  ключи: %s" % ", ".join(sorted(выз[-1].keys())))
