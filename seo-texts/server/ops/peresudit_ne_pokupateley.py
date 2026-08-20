# -*- coding: utf-8 -*-
"""Пересудить всех «не покупатель» заново — теперь с паспортом сайта.

Замер на десяти показал: шесть из десяти снятых гейтом на самом деле
покупатели, и опровержение лежало в паспорте той же компании. Кэш гейта
вечен — judge() отдаёт вердикт по ИНН и заново не судит, поэтому без
пересуда правка не поможет никому из уже осуждённых.

Старые вердикты сохраняем на диск ДО правки: решение владельца можно
будет откатить, а разбор — перепроверить.

Без --katit только показывает.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.target_gate import (НЕ_ПОКУПАТЕЛЬ, НЕЯСНО,           # noqa: E402
                                ПОКУПАТЕЛЬ)

БЭКАП = r"C:\sender\_ops\target-verdicts-do-pasporta.jsonl"
ЖУРНАЛ = r"C:\sender\_ops\peresud-geyta.jsonl"
ШАГ = 10
КАТИТЬ = "--katit" in sys.argv
ПОТОЛОК = int(next((a for a in sys.argv[1:] if a.isdigit()), "0"))

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
гейт = q._gate()
if гейт is None:
    print("гейт не собрался")
    raise SystemExit(2)

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT tv.inn, tv.verdict, COALESCE(tv.chem,'') chem, "
    "       COALESCE(tv.pochemu,'') pochemu, COALESCE(tv.source,'') src, "
    "       tv.ts, "
    "       (SELECT company_name FROM recipients WHERE inn=tv.inn LIMIT 1) имя, "
    "       (SELECT okved FROM recipients WHERE inn=tv.inn LIMIT 1) оквэд "
    "FROM target_verdicts tv WHERE tv.verdict='не покупатель' "
    "ORDER BY tv.ts DESC").fetchall()

# Бэкап старых вердиктов — до единой правки.
if not os.path.exists(БЭКАП):
    with io.open(БЭКАП, "w", encoding="utf-8") as ж:
        for r in ряды:
            ж.write(json.dumps({k: r[k] for k in r.keys()},
                               ensure_ascii=False, default=str) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    print(f"бэкап старых вердиктов: {БЭКАП} ({len(ряды)} строк)")

работа, без_паспорта = [], 0
for r in ряды:
    инн = str(r["inn"])
    п = q._pasport_dlya_geyta(инн)
    if not п:
        без_паспорта += 1
        continue
    карточка = q._card_for(инн) or {}
    ec = (карточка.get("enrich") or {}).get("company") or {}
    работа.append({
        "inn": инн,
        "name": str(r["имя"] or "") or ec.get("name") or "",
        "okved": str(r["оквэд"] or "") or ec.get("okved") or "",
        "activity": ec.get("activity") or "",
        "pasport": п,
    })
if ПОТОЛОК:
    работа = работа[:ПОТОЛОК]
print(f"«не покупатель» всего: {len(ряды)} | с паспортом: {len(работа)} | "
      f"без паспорта (не трогаем): {без_паспорта}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

счёт = Counter()
вернули = []
СТАРТ = time.time()
for i in range(0, len(работа), ШАГ):
    часть = работа[i:i + ШАГ]
    try:
        п = гейт._партия(часть, "продавец")
        с = гейт._партия(часть, "скептик")
    except Exception as ex:                                      # noqa: BLE001
        print(f"  пачка {i}: сбой {type(ex).__name__} {str(ex)[:90]}")
        счёт["пачка не прошла"] += len(часть)
        continue
    строки = []
    for к in часть:
        инн = к["inn"]
        вп = (п.get(инн) or {}).get("verdict")
        вс = (с.get(инн) or {}).get("verdict")
        if вп == вс == НЕ_ПОКУПАТЕЛЬ:
            новый = НЕ_ПОКУПАТЕЛЬ
        elif ПОКУПАТЕЛЬ in (вп, вс):
            новый = ПОКУПАТЕЛЬ
        else:
            новый = НЕЯСНО
        чем = ((п.get(инн) or {}).get("chem")
               or (с.get(инн) or {}).get("chem") or "")
        почему = ((с.get(инн) or {}).get("pochemu") if новый == НЕ_ПОКУПАТЕЛЬ
                  else (п.get(инн) or {}).get("pochemu")) or ""
        счёт[f"не покупатель -> {новый}"] += 1
        if новый != НЕ_ПОКУПАТЕЛЬ:
            вернули.append((инн, к["name"], новый))
        try:
            гейт._save(инн, новый, str(чем)[:200], str(почему)[:300],
                       "пересуд с паспортом")
        except Exception as ex:                                  # noqa: BLE001
            print(f"  #{инн} вердикт не записался: {str(ex)[:80]}")
        строки.append({"inn": инн, "имя": к["name"], "было": "не покупатель",
                       "стало": новый, "почему": str(почему)[:200]})
    with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
        for z in строки:
            ж.write(json.dumps(z, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    print(f"  {i + len(часть)}/{len(работа)} за {int(time.time() - СТАРТ)} с")

print(f"\nитог за {int(time.time() - СТАРТ)} с: {dict(счёт)}")
print(f"вернулось в работу: {len(вернули)}")
for инн, имя, в in вернули[:40]:
    print(f"  {инн}  {str(имя)[:44]:<44} -> {в}")
