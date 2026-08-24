# -*- coding: utf-8 -*-
"""Что сейчас генерируется: прогоны, направление, кэш.

Владелец 24.08: «какие сейчас в очереди на генерацию идут? есть ли там
мейер? читается ли кеш?». Печатаем живые процессы с их аргументами
(направление видно по --корп/--группа/потолку), ход по журналу и разбор
чтения кэша по последним записям.
"""
import glob
import io
import json
import os
import subprocess
import time
from collections import Counter

print("=== ЖИВЫЕ ПРОГОНЫ ===")
из = subprocess.run(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
     "Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Csv "
     "-NoTypeInformation"],
    capture_output=True, text=True, timeout=120)
живых = 0
for строка in (из.stdout or "").splitlines():
    if "partiya_gen" in строка or "dopisat" in строка or "regen" in строка:
        живых += 1
        print("  " + строка.strip()[:230])
if not живых:
    print("  прогонов генерации в процессах НЕТ")

print("\n=== ЖУРНАЛЫ ПАРТИЙ ===")
for п in sorted(glob.glob(r"C:\sender\_ops\gen-*.jsonl"),
                key=lambda x: -os.path.getmtime(x)):
    возраст = (time.time() - os.path.getmtime(п)) / 60.0
    записи = []
    try:
        for с in io.open(п, encoding="utf-8"):
            с = с.strip()
            if с:
                try:
                    записи.append(json.loads(с))
                except Exception:  # noqa: BLE001
                    pass
    except Exception as e:  # noqa: BLE001
        print("  %s: не прочитан (%s)" % (os.path.basename(п), e))
        continue
    сег = [з for з in записи
           if str(з.get("когда") or з.get("ts") or "")[:10] == "2026-08-24"]
    виды = Counter(str(з.get("событие") or з.get("что") or "?") for з in записи)
    print("\n  %s — %d записей, обновлён %.1f мин назад"
          % (os.path.basename(п), len(записи), возраст))
    print("    события: %s" % ", ".join("%s=%d" % (к, н)
                                        for к, н in виды.most_common(6)))
    print("    за сегодня: %d" % len(сег))
    if записи:
        п_ = записи[-1]
        print("    последняя: %s" % json.dumps(п_, ensure_ascii=False)[:230])

print("\n=== НАПРАВЛЕНИЕ: ЧТО В ОЧЕРЕДИ ПОДТВЕРЖДЕНИЯ ПО ЯЩИКАМ ===")
import sqlite3
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
for р in c.execute(
        "SELECT COALESCE(cr.mailbox_id, m.mailbox_id, '(не выбран)') я, "
        "       cr.status, COUNT(*) n FROM confirm_reviews cr "
        "  LEFT JOIN messages m ON m.id = cr.message_id "
        " WHERE cr.status IN ('pending','approved') "
        " GROUP BY я, cr.status ORDER BY n DESC LIMIT 18"):
    домен = str(р["я"]).split("@")[-1]
    напр = ("MEYER" if any(к in домен for к in ("sort", "optic", "meyer", "usort"))
            else "КЦ" if "kompressor" in домен or "compressor" in домен else "?")
    print("  %-38s %-10s %5d   %s" % (str(р["я"])[:38], р["status"], р["n"], напр))

print("\n=== СВЕЖИЕ ПИСЬМА ПО НАПРАВЛЕНИЯМ (созданы сегодня) ===")
свод = Counter()
for р in c.execute(
        "SELECT COALESCE(m.mailbox_id,'') я FROM confirm_reviews cr "
        "  LEFT JOIN messages m ON m.id=cr.message_id "
        " WHERE substr(cr.created_at,1,10)=date('now')"):
    д = str(р["я"]).split("@")[-1]
    свод["MEYER" if any(к in д for к in ("sort", "optic", "meyer", "usort"))
         else "КЦ" if ("kompressor" in д or "compressor" in д) else "не выбран"] += 1
for к, н in свод.most_common():
    print("  %-12s %d" % (к, н))
