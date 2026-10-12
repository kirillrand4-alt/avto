# -*- coding: utf-8 -*-
"""Как идёт генерация 500: прогресс, живость работника, очередь, модели."""
import io
import json
import os
import sqlite3
import subprocess
from collections import Counter

пр = {}
try:
    пр = json.load(io.open(r"C:\sender\_ops\gen500-progress.json", encoding="utf-8"))
except Exception as e:  # noqa: BLE001
    print("прогресса нет: %s" % e)
pid = io.open(r"C:\sender\_ops\gen500.pid").read().strip() if os.path.exists(
    r"C:\sender\_ops\gen500.pid") else ""
жив = False
if pid:
    вывод = subprocess.run(["tasklist", "/FI", "PID eq %s" % pid],
                           capture_output=True, text=True).stdout
    жив = pid in вывод
камп = int(пр.get("кампания") or 14)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
в_очереди = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=? "
                      "AND status='pending'", (камп,)).fetchone()[0]
модели = Counter()
for р in c.execute("SELECT panel_json FROM confirm_reviews WHERE campaign_id=?",
                   (камп,)):
    try:
        модели[(json.loads(р["panel_json"] or "{}") or {}).get("model_pisma")
               or "(без подписи)"] += 1
    except Exception:  # noqa: BLE001
        модели["(панель не читается)"] += 1
хвост = ""
try:
    т = io.open(r"C:\sender\_ops\gen500.log", encoding="utf-8",
                errors="replace").read()
    хвост = т[-700:]
except Exception:  # noqa: BLE001
    pass
print("лог работника (хвост):")
print(хвост)
print("")
print("модели писем в очереди:")
for м, n in модели.most_common():
    print("   %-40s %4d" % (м, n))
print("")
print("=== ГЕНЕРАЦИЯ 500 ===")
print("   этап: %s, обновлено %s" % (пр.get("этап"), пр.get("ts")))
print("   работник pid %s жив: %s" % (pid, жив))
print("   готово %s, брак %s из %s"
      % (пр.get("готово"), пр.get("брак"), пр.get("получателей")))
print("   в очереди подтверждения (кампания %d): %d" % (камп, в_очереди))
if пр.get("ошибки"):
    print("   ошибки: %s" % пр.get("ошибки"))
