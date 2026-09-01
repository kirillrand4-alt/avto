# -*- coding: utf-8 -*-
"""Сколько свободных кандидатов в группе «Партия 935» под фильтром выручки.

Повторяет отбор partiya_gen.py ровно до направления: группа, карточка,
почта, приговор пробы, предпросев, дубль ИНН, выручка, резюм по журналу,
три попытки. Направление здесь считаем по метке обогащения (в прогоне его
считает цепочка запроса — это стоит вызовов, тут не нужно).
"""
import io
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
ГРУППА = "Партия 935"
ПОРОГ = 30_000_000

try:
    вых = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*partiya_gen*' }).Count"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    print("живых прогонов partiya_gen: %s" % (вых or "0"))
except Exception as ex:  # noqa: BLE001
    print("не удалось посчитать прогоны: %s" % str(ex)[:80])

# --- резюм по журналу, ключ ЛАТИНСКИЙ inn (как в прогоне) ---------------
сделано_инн, попыток = set(), Counter()
if os.path.exists(ЖУРНАЛ):
    for стр in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(стр)
        except Exception:  # noqa: BLE001
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
print("журнал: фирм с письмом %d, фирм с попытками %d"
      % (len(сделано_инн), len(попыток)))

# --- выручка и направление из обогащения --------------------------------
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True,
                    timeout=90)
выручка, дивизион = {}, {}
for и, в, d in e.execute("SELECT inn, revenue_rub, division FROM companies"):
    ц = "".join(c for c in str(и or "") if c.isdigit())
    if ц:
        выручка[ц] = в
        дивизион[ц] = (d or "").lower()
e.close()
print("обогащение: выручка известна у %d компаний" % len(выручка))

from sender.config import Config           # noqa: E402
from sender.store import Store             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
группы = store.recipient_groups().get("по_id") or {}
в_группе = sorted(rid for rid, gr in группы.items() if ГРУППА in gr)
print("строк в группе «%s»: %d" % (ГРУППА, len(в_группе)))

счёт = Counter()
видели, свободные_meyer, ниже_порога = set(), set(), set()
от_porogа, neizvestnye = set(), set()
for rid in в_группе:
    rec = store.get_recipient(rid)
    if not rec:
        счёт["строки без карточки"] += 1
        continue
    inn = "".join(c for c in str(getattr(rec, "inn", "") or "")
                  if c.isdigit())
    email = str(getattr(rec, "email", "") or "").strip().lower()
    if not inn or not email:
        счёт["без ИНН или почты"] += 1
        continue
    снят = str((getattr(rec, "extra", None) or {}).get("ne_nash_ni_odnomu")
               or "").strip()
    if снят:
        счёт["предпросев: нет производства"] += 1
        continue
    if inn in видели:
        счёт["дубль строки той же фирмы"] += 1
        continue
    видели.add(inn)
    if "meyer" not in дивизион.get(inn, ""):
        счёт["не мейер по метке базы"] += 1
        continue
    счёт["мейеровских фирм в группе"] += 1
    в = выручка.get(inn)
    известна = в is not None and int(в or 0) > 0
    if известна and int(в) < ПОРОГ:
        ниже_порога.add(inn)
        счёт["выручка ниже порога"] += 1
        continue
    if inn in сделано_инн:
        счёт["письмо уже есть"] += 1
        continue
    if попыток[inn] >= 3:
        счёт["исчерпал 3 попытки"] += 1
        continue
    свободные_meyer.add(inn)
    (от_porogа if известна else neizvestnye).add(inn)

print("")
print("=== ВОРОНКА ГРУППЫ ===")
for к, в in счёт.most_common():
    print("   %-36s %7d" % (к, в))
print("")
print("=== СВОБОДНЫХ ПОД ФИЛЬТРОМ ВЫРУЧКИ ===")
print("   годных к генерации:          %7d" % len(свободные_meyer))
print("      из них выручка ОТ 30 МЛН: %7d   <- строгий режим" % len(от_porogа))
print("      из них выручка НЕ известна:%7d" % len(neizvestnye))
print("   отсеяно порогом (30 млн):    %7d" % len(ниже_порога))
