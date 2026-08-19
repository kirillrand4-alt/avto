# -*- coding: utf-8 -*-
"""Письмо целиком + откуда у него взялся такой заход и обращение.

Владелец по #1240: «откуда то вылезло "Андрей Лещев" обращение по имени и
фамилии» и «такие заходы не понравились редактору, раньше таких не было».
Смотрим само письмо, запись журнала перезаписи (что было до) и что в
правилах разрешает такой зачин.
"""
import io
import json
import re
import sys

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AI                               # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

RID = int(next((a for a in sys.argv[1:] if a.isdigit()), "1240"))
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

row = store.confirm_get(RID) or {}
print(f"#{RID}  {row.get('email')}  статус {row.get('status')}  "
      f"кампания {row.get('campaign_id')}")
rec = store.get_recipient(int(row.get("recipient_id") or 0))
if rec:
    print(f"получатель: {getattr(rec, 'company_name', '')} | "
          f"контактное лицо: {getattr(rec, 'contact_name', '')!r}")
print("\nТЕМА:", row.get("subject"))
print("\n" + (row.get("body") or "")[:1800])

for ж, имя in ((r"C:\sender\_ops\peregeneraciya-meyer.jsonl", "перезапись Meyer"),
               (r"C:\sender\_ops\dopisannye-zachiny.jsonl", "дописывание зачинов"),
               (r"C:\sender\_ops\gen-partiya-935.jsonl", "партийная генерация")):
    try:
        for s in io.open(ж, encoding="utf-8", errors="replace"):
            try:
                z = json.loads(s)
            except Exception:                                    # noqa: BLE001
                continue
            if int(z.get("id") or z.get("review_id") or 0) == RID:
                print(f"\n--- {имя}: ок={z.get('ок')} "
                      f"почему={str(z.get('почему'))[:80]}")
                if z.get("тело_до"):
                    print("БЫЛО:", (z.get("тело_до") or "")[:700])
    except FileNotFoundError:
        pass

print("\n--- что в правилах про ХАССП/аудит/сети ---")
for div in ("meyer", "kc"):
    т = AI.RULES_BY_DIVISION[div]
    for m in re.finditer(r'(?i)[^\n]*(хассп|haccp|аудит|торговых сет|сетев)[^\n]*',
                         т):
        print(f"  [{div}] {m.group(0).strip()[:110]}")

print("\n--- что в правилах про обращение по имени ---")
for div in ("meyer",):
    т = AI.RULES_BY_DIVISION[div]
    for m in re.finditer(r'(?i)[^\n]*(по имени|имя.отчеств|фамили|обращени)[^\n]*',
                         т):
        print(f"  [{div}] {m.group(0).strip()[:110]}")
