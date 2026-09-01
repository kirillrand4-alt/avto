# -*- coding: utf-8 -*-
"""Сколько компаний строгого пула уже имеют вердикт гейта в кэше.

От этого зависит, через сколько прогон начнёт писать: непросуженных он
гонит в провайдера пачками по 8, и только набрав потолок выживших,
переходит к письмам. Сводка в конце.
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ГРУППА = "Партия 935"
ПОРОГ = 30_000_000

сделано_инн, попыток = set(), Counter()
for стр in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(стр)
    except Exception:                                          # noqa: BLE001
        continue
    inn = str(z.get("inn") or "")
    if not inn:
        continue
    if z.get("этап") == "отмена_попытки":
        попыток[inn] = max(0, попыток[inn] - 1)
        continue
    if z.get("этап") != "итог":
        попыток[inn] += 1
    if z.get("ок") or z.get("тело"):
        сделано_инн.add(inn)

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
выручка, дивизион = {}, {}
for и, в, d in e.execute("SELECT inn, revenue_rub, division FROM companies"):
    ц = "".join(c for c in str(и or "") if c.isdigit())
    if ц:
        выручка[ц] = в
        дивизион[ц] = (d or "").lower()
e.close()

from sender.config import Config                               # noqa: E402
from sender.store import Store                                 # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)

строгие, видели = set(), set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "") if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email or inn in видели:
        continue
    if str((getattr(rec, "extra", None) or {}).get("ne_nash_ni_odnomu") or ""):
        continue
    видели.add(inn)
    if "meyer" not in дивизион.get(inn, ""):
        continue
    в = выручка.get(inn)
    if not (в is not None and int(в or 0) >= ПОРОГ):
        continue
    if inn in сделано_инн or попыток[inn] >= 3:
        continue
    строгие.add(inn)

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
кэш = {}
for и, в in s.execute("SELECT inn, verdict FROM target_verdicts"):
    ц = "".join(c for c in str(и or "") if c.isdigit())
    if ц:
        кэш[ц] = в
s.close()

есть = {и: кэш[и] for и in строгие if и in кэш}
нет = строгие - set(есть)
по_видам = Counter(есть.values())
покупатели = по_видам.get("покупатель", 0)

print("=" * 64)
print("=== СВОДКА: СТРОГИЙ ПУЛ И КЭШ ГЕЙТА ===")
print("свободных компаний с выручкой ОТ 30 МЛН: %d" % len(строгие))
print("")
print("   уже просужены гейтом:  %5d (%.0f%%)"
      % (len(есть), 100.0 * len(есть) / len(строгие) if строгие else 0))
for к, в in по_видам.most_common():
    print("      %-16s %5d" % (к, в))
print("   ещё не просужены:      %5d" % len(нет))
print("")
print("К ПИСЬМАМ ГОДНЫ СРАЗУ (кэш «покупатель»): %d" % покупатели)
print("Остальным гейт спросит провайдера: %d компаний, темп ~1800 в час"
      % len(нет))
print("   это примерно %.1f часа гейта до полного покрытия"
      % (len(нет) / 1800.0))
