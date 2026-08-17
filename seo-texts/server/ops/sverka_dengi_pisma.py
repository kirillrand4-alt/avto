# -*- coding: utf-8 -*-
"""Ровно ли то, за что заплачено, лежит в панели. И нет ли лишних прогонов.

Владелец 17.08: «проверь что ровно то что заплатим в итоге идёт в панель,
нет лишних прогонов». Вопрос из трёх, и каждый меряется отдельно.

1. ЛИШНИЕ ПРОГОНЫ. Серверный процесс переживает смерть местного драйвера, и
   два круга идут по одному списку: письмо пишется дважды, а в очередь его
   пустят один раз (UNIQUE dedup_key inn|email|campaign) - вторая генерация
   оплачена и выброшена. Считаем живые процессы.

2. ДВОЙНАЯ ОПЛАТА В ЖУРНАЛЕ. Тот же ИНН с двумя записями «сгенерировано» -
   это и есть след параллельных кругов, уже в деньгах. Считаем повторы и их
   цену.

3. ЧТО ДОЕХАЛО. Каждая запись «итог» с ок=1 называет review_id. Проверяем
   поимённо, что строка есть в confirm_reviews, и раскладываем расход на
   три кучи: доехало, брак (гейт забраковал - письма нет), потеряно
   (оплачено, review_id назван, а строки нет - вот это настоящая беда).

    python zapusk_svoego_skripta.py ops/sverka_dengi_pisma.py
"""
import io
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
МЕТКИ = ("_gen_partiya", "partiya_gen")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# --- 1. живые прогоны ------------------------------------------------------ #
живые = []
try:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "ForEach-Object { \"$($_.ProcessId)|$($_.CreationDate.ToString('s'))|"
         "$($_.CommandLine)\" }"],
        capture_output=True, text=True, timeout=90).stdout
    for l in out.splitlines():
        if any(м in l for м in МЕТКИ):
            ч = l.split("|", 2)
            живые.append((ч[0].strip(), ч[1].strip() if len(ч) > 1 else "?"))
except Exception as ex:                                         # noqa: BLE001
    print("процессы не опрошены:", str(ex)[:120])

print(f"1) ЖИВЫХ ПРОГОНОВ ГЕНЕРАЦИИ: {len(живые)}")
for pid, старт in живые:
    print(f"   pid {pid} старт {старт}")
if len(живые) > 1:
    print("   ЛИШНИЕ ЕСТЬ: ops/partiya_ubit_lishniy.py оставит самый свежий")
elif len(живые) == 1:
    print("   ровно один - как надо")
else:
    print("   ни одного (круг между чанками или прогон закончен)")

# --- 2. журнал: повторная оплата ------------------------------------------- #
записей_текста = defaultdict(list)      # инн -> [цена, ...]
итоги = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                       # noqa: BLE001
            continue
        inn = str(z.get("inn") or "")
        if z.get("этап") == "сгенерировано":
            записей_текста[inn].append(float(z.get("цена_$") or 0))
        elif z.get("этап") == "итог":
            итоги.append(z)

повторы = {i: ц for i, ц in записей_текста.items() if len(ц) > 1}
цена_повторов = sum(sum(ц[1:]) for ц in повторы.values())
всего_цена = sum(sum(ц) for ц in записей_текста.values())
print(f"\n2) ЖУРНАЛ: компаний с текстом {len(записей_текста)}, "
      f"записей {sum(len(ц) for ц in записей_текста.values())}")
print(f"   потрачено всего: ${всего_цена:.2f}")
print(f"   компаний, которым писали БОЛЬШЕ ОДНОГО РАЗА: {len(повторы)}")
print(f"   цена вторых и следующих попыток: ${цена_повторов:.2f}")
print("   ВНИМАНИЕ: повтор повтору рознь. Законный - когда первое письмо ушло")
print("   в брак и конвейер пишет заново (до трёх попыток на ИНН). Пустой -")
print("   когда два параллельных круга пишут одной фирме одновременно.")
print("   Различаем по итогам: если среди попыток ИНН есть брак, повтор")
print("   законный.")
_законных = _pustyh = 0
_ц_законных = _ц_pustyh = 0.0
_итогов_инн = defaultdict(list)
for z in итоги:
    _итогов_инн[str(z.get("inn") or "")].append(bool(z.get("ок")))
for i, ц in повторы.items():
    было_брака = any(not ок for ок in _итогов_инн.get(i, []))
    if было_брака:
        _законных += 1
        _ц_законных += sum(ц[1:])
    else:
        _pustyh += 1
        _ц_pustyh += sum(ц[1:])
print(f"   законных повторов (после брака): {_законных}, ${_ц_законных:.2f}")
print(f"   ПУСТЫХ повторов (все попытки удачны - значит писали дважды "
      f"зря): {_pustyh}, ${_ц_pustyh:.2f}")
for i, ц in list(повторы.items())[:8]:
    print(f"     ИНН {i}: {len(ц)} раза, ${sum(ц):.3f}")

# --- 3. что доехало в панель ----------------------------------------------- #
куча = Counter()
деньги = Counter()
названные = {}
# ЦЕНА У КАЖДОЙ ПОПЫТКИ СВОЯ. Первая редакция приписывала каждому «итогу»
# ВСЮ сумму по ИНН, и у компаний с повторами деньги считались дважды: итог
# вышел $86.30 при фактических $62.31 в журнале. Пары «сгенерировано» ->
# «итог» идут по журналу подряд для одного ИНН, поэтому держим на ИНН
# очередь неразобранных цен и снимаем по одной.
_очередь_цен = defaultdict(list)
for inn, цены in записей_текста.items():
    _очередь_цен[inn] = list(цены)


def _цена(inn):
    оч = _очередь_цен.get(inn) or []
    return оч.pop(0) if оч else 0.0


for z in итоги:
    inn = str(z.get("inn") or "")
    ц = _цена(inn)
    if z.get("ок") and z.get("review_id"):
        названные[int(z["review_id"])] = ц
    elif z.get("ок"):
        куча["ок, но review_id не назван"] += 1
        деньги["ок, но review_id не назван"] += ц
    else:
        куча["брак: письма в панели нет"] += 1
        деньги["брак: письма в панели нет"] += ц

есть = set()
if названные:
    ids = list(названные)
    with store._lock:
        for i in range(0, len(ids), 400):
            часть = ids[i:i + 400]
            метки = ",".join("?" * len(часть))
            есть |= {r[0] for r in store._conn.execute(
                f"SELECT id FROM confirm_reviews WHERE id IN ({метки})", часть)}
for rid, ц in названные.items():
    if rid in есть:
        куча["ДОЕХАЛО в панель"] += 1
        деньги["ДОЕХАЛО в панель"] += ц
    else:
        куча["ПОТЕРЯНО: оплачено, строки нет"] += 1
        деньги["ПОТЕРЯНО: оплачено, строки нет"] += ц

print("\n3) КУДА УШЛИ ДЕНЬГИ")
for k, n in куча.most_common():
    print(f"   {k:<34} {n:>5} писем  ${деньги[k]:.2f}")
итого_писем = sum(куча.values())
print(f"   {'ИТОГО':<34} {итого_писем:>5} писем  ${sum(деньги.values()):.2f}")
if куча["ПОТЕРЯНО: оплачено, строки нет"]:
    print("   ЕСТЬ ПОТЕРИ - прогон надо остановить и разобраться")
else:
    print("   потерь нет: всё оплаченное либо в панели, либо честно "
          "забраковано гейтом")
