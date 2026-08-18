# -*- coding: utf-8 -*-
"""По каким признакам письмо НЕ попало в сегодняшнюю отправку — числами.

Вопрос владельца 18.08: «разбери критерии, по которым сегодня мы не стали
переводить в очередь отправок письма, и как мы добились баунсов 1%».

Отсев многоступенчатый, и каждая ступень оставляет свой след:
  1) отбор кандидатов  — нецелевые ОКВЭД, гейт покупателей, мёртвые адреса;
  2) генерация         — брак по механическому QA (журнал партии);
  3) рецензент по сайту— «годно / не годно» с причиной (журнал рецензий);
  4) очередь           — snято/стоп-лист с причиной (confirm_reviews.reason);
  5) отправка          — заслоны рассыльщика (события skip/suppress).

    python zapusk_svoego_skripta.py ops/kriterii_otbora_segodnya.py
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))


def _чисто(причина: str) -> str:
    """Схлопнуть причину до вида, по которому можно считать."""
    т = str(причина or "").strip()
    т = re.sub(r"\d{4,}", "…", т)
    т = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+", "<адрес>", т)
    return т[:70] or "(без причины)"


print("=== 4. ОЧЕРЕДЬ: почему письма сняты (confirm_reviews)")
with store._lock:
    ряд = store._conn.execute(
        "SELECT status, COALESCE(reason,''), COUNT(*) FROM confirm_reviews "
        "GROUP BY status, reason ORDER BY 3 DESC").fetchall()
по_статусу = Counter()
причины = Counter()
for ст, причина, n in ряд:
    по_статусу[ст] += n
    if ст in ("skipped", "stoplist"):
        причины[_чисто(причина)] += n
print("  всего по статусам:", dict(по_статусу))
print("  причины снятия:")
for п, n in причины.most_common(20):
    print(f"    {n:>5}  {п}")

print("\n=== 3. РЕЦЕНЗЕНТ ПО САЙТУ (журнал рецензий)")
ж = r"C:\sender\_ops\rezenzii-pisem.jsonl"
if os.path.exists(ж):
    вердикты = Counter()
    причины_р = Counter()
    видел = set()
    for s in io.open(ж, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
        except Exception:                                        # noqa: BLE001
            continue
        cid = z.get("id") or z.get("confirm_id")
        if cid in видел:
            continue
        видел.add(cid)
        в = str(z.get("вердикт") or z.get("verdict") or "?")
        вердикты[в] += 1
        if в not in ("годно", "ok", "годен"):
            for ч in (z.get("причины") or z.get("замечания") or
                      [z.get("причина") or ""]):
                if ч:
                    причины_р[_чисто(str(ч))] += 1
    print(f"  писем отрецензировано: {len(видел)}")
    print("  вердикты:", dict(вердикты.most_common()))
    print("  причины «не годно» (топ-20):")
    for п, n in причины_р.most_common(20):
        print(f"    {n:>5}  {п}")
else:
    print(f"  журнала нет: {ж}")

print("\n=== 2. ГЕНЕРАЦИЯ: брак механического QA (журнал партии)")
жг = r"C:\sender\_ops\gen-partiya-935.jsonl"
if os.path.exists(жг):
    брак = Counter()
    попыток = ок = 0
    for s in io.open(жг, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
        except Exception:                                        # noqa: BLE001
            continue
        if z.get("этап") in ("итог", "отмена_попытки"):
            continue
        попыток += 1
        if z.get("ок"):
            ок += 1
        for б in (z.get("брак") or []):
            брак[_чисто(str(б))] += 1
    print(f"  попыток генерации: {попыток}, из них удачных: {ок}")
    print("  причины брака (топ-15):")
    for п, n in брак.most_common(15):
        print(f"    {n:>5}  {п}")
else:
    print(f"  журнала нет: {жг}")

print("\n=== 1. ОТБОР КАНДИДАТОВ: вердикты гейта покупателей")
with store._lock:
    try:
        г = store._conn.execute(
            "SELECT verdict, COUNT(*) FROM target_verdicts GROUP BY verdict "
            "ORDER BY 2 DESC").fetchall()
        for в, n in г:
            print(f"    {n:>5}  {в}")
    except Exception as ex:                                      # noqa: BLE001
        print("  target_verdicts:", str(ex)[:100])

print("\n=== ПРОБА АДРЕСОВ: вердикты в кэше")
with store._lock:
    п = store._conn.execute(
        "SELECT verdict, COUNT(*) FROM addr_probe GROUP BY verdict "
        "ORDER BY 2 DESC").fetchall()
for в, n in п:
    print(f"    {n:>5}  {в}")
