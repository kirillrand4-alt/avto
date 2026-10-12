# -*- coding: utf-8 -*-
"""Поправить отраслевую боль по зерну: беды культур берём из meyer_bedy.

Владелец 12.10: «там точный список болей под зерновых был» — это таблица
meyer_bedy (его же таблица и слайд от 14.08: фузариоз, овсюг, амброзия,
эгилопс и далее по культурам). Отраслевая строка не должна с ней спорить
и подсовывать выдуманные беды вроде спорыньи.
"""
import io
import json
import os
import shutil
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender import ai_letter as AL                               # noqa: E402

НОВАЯ = ("отбор зерна и семян по цвету и форме на приёмке и перед отгрузкой: "
         "труднотделимые засорители и поражённое зерно, которые обычная "
         "очистка не берёт (конкретные беды культуры подставляет таблица "
         "meyer_bedy — своими словами их не придумывать)")
КЛЮЧ = "Зерно, мука, элеваторы, семена"

ФАЙЛ = AL.OKVED_PAINS_PATH
д = json.load(io.open(ФАЙЛ, encoding="utf-8"))
было = (д.get("_по_отрасли") or {}).get(КЛЮЧ, "")
shutil.copy2(ФАЙЛ, ФАЙЛ + ".bak-%d" % int(time.time()))
д.setdefault("_по_отрасли", {})[КЛЮЧ] = НОВАЯ
json.dump(д, io.open(ФАЙЛ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("файл: %s" % ФАЙЛ)
print("было:  %s" % было[:120])
print("стало: %s" % НОВАЯ[:120])

try:
    from sender.meyer_bedy import БЕДЫ
    print("культур в таблице бед: %d (%s)"
          % (len(БЕДЫ), ", ".join(sorted(БЕДЫ))))
except Exception as e:  # noqa: BLE001
    print("таблицу бед прочитать не вышло: %s" % e)
print("")
print("=== ОТРАСЛЕВАЯ БОЛЬ ПО ЗЕРНУ ПОПРАВЛЕНА ===")
