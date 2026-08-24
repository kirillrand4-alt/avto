# -*- coding: utf-8 -*-
"""Паспорта пяти компаний целиком — хватает ли их на шаблон.

Владелец спросил, можно ли по паспорту собрать максимально приближенный
шаблон. Ответ зависит от того, что в паспорте лежит: конкретика про цех и
продукцию — можно, общие слова с главной страницы — нет.
"""
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб",
        "мощности")

группы = store.recipient_groups().get("по_id") or {}
взяли = 0
for rid, gr in sorted(группы.items()):
    if "Партия 935" not in gr:
        continue
    rec = store.get_recipient(rid)
    if not rec or not getattr(rec, "inn", None):
        continue
    d = {}
    try:
        d = q._site_facts(rec.inn) or {}
    except Exception:  # noqa: BLE001
        d = {}
    полей = sum(1 for к in ПОЛЯ if d.get(к))
    if полей < 4:
        continue
    взяли += 1
    print("\n=== %s (ИНН %s, полей %d) ==="
          % (str(getattr(rec, "company_name", ""))[:50], rec.inn, полей))
    print("  ОКВЭД: %s" % str(getattr(rec, "okved", "") or "-"))
    for к in ПОЛЯ:
        v = d.get(к)
        if not v:
            continue
        текст = v if isinstance(v, str) else "; ".join(map(str, v))
        print("  %-20s %s" % (к + ":", текст[:400]))
    if взяли >= 4:
        break

print("\n=== СРЕДНЯЯ ДЛИНА ПОЛЕЙ ПО ПУЛУ (200 компаний) ===")
from collections import Counter
длины = {к: [] for к in ПОЛЯ}
сколько = 0
for rid, gr in sorted(группы.items()):
    if "Партия 935" not in gr or сколько >= 200:
        continue
    rec = store.get_recipient(rid)
    if not rec or not getattr(rec, "inn", None):
        continue
    try:
        d = q._site_facts(rec.inn) or {}
    except Exception:  # noqa: BLE001
        continue
    сколько += 1
    for к in ПОЛЯ:
        v = d.get(к)
        if v:
            длины[к].append(len(v if isinstance(v, str)
                                else "; ".join(map(str, v))))
for к in ПОЛЯ:
    з = длины[к]
    print("  %-20s заполнено у %3d из %d, средняя длина %4d знаков"
          % (к, len(з), сколько, (sum(з) // len(з)) if з else 0))
