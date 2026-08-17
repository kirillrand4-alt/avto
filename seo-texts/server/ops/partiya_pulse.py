# -*- coding: utf-8 -*-
"""Пульс прогона: что реально произошло за последние минуты.

Владелец 17.08: «письма не растут в панели». Отвечать на это надо не
рассуждением, а тремя срезами разом, снятыми в один момент: сколько строк
журнала за последние минуты, сколько карточек в очереди по кампаниям и
какие процессы генерации сейчас живут на сервере.

Ничего не меняет.
"""
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
МИНУТ = int(sys.argv[1]) if len(sys.argv) > 1 else 30

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("сейчас на сервере:", time.strftime("%Y-%m-%d %H:%M:%S"))

# --- 1. журнал -----------------------------------------------------------
строки = []
if os.path.exists(Ж):
    строки = [json.loads(s) for s in io.open(Ж, encoding="utf-8") if s.strip()]
    print(f"\nжурнал: {len(строки)} строк, изменён "
          + time.strftime("%H:%M:%S", time.localtime(os.path.getmtime(Ж))))
    этапы = Counter(str(z.get("этап") or "без этапа") for z in строки)
    print("  этапы:", dict(этапы))
    хвост = строки[-8:]
    print("  последние строки:")
    for z in хвост:
        print(f"    {str(z.get('этап') or '?'):<14} "
              f"{str(z.get('имя'))[:26]:<28} ок={z.get('ок')} "
              f"rev={z.get('review_id')} ${z.get('цена_$')} "
              f"{z.get('сек')}с | {str((z.get('брак') or [''])[0])[:60]}")
else:
    print("журнала нет")

# --- 2. очередь панели ---------------------------------------------------
print("\nочередь панели:")
всего = Counter()
свежие = 0
порог = time.time() - МИНУТ * 60
for ст in ("pending", "approved", "sent", "skipped"):
    ряд = store.confirm_list(status=ст, limit=100000) or []
    for r in ряд:
        c = int(r.get("campaign_id") or 0)
        if c in (10, 11):
            всего[f"{ст} к{c}"] += 1
            try:
                t = datetime.fromisoformat(str(r.get("created_at")))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t.timestamp() >= порог:
                    свежие += 1
            except Exception:                                  # noqa: BLE001
                pass
for k, n in sorted(всего.items()):
    print(f"  {k:<16} {n}")
print(f"  СОЗДАНО ЗА ПОСЛЕДНИЕ {МИНУТ} МИН: {свежие}")

# --- 3. живые процессы ---------------------------------------------------
print("\nпроцессы python на сервере:")
try:
    out = subprocess.run(
        ["wmic", "process", "where", "name='python.exe'",
         "get", "ProcessId,CommandLine"],
        capture_output=True, text=True, timeout=60).stdout
    for s in out.splitlines():
        s = s.strip()
        if s and ("_ops" in s or "sender" in s):
            print("  " + s[:160])
except Exception as ex:                                        # noqa: BLE001
    print("  не спросилось:", str(ex)[:90])
