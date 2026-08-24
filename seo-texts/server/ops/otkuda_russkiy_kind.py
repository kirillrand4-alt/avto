# -*- coding: utf-8 -*-
"""Кто пишет в лид русские метки «отказ»/«автоответ».

Классификатор отдаёт только английские метки (ALL_KINDS), а в базе лежат
русские. Значит, метку ставит какой-то другой путь. Ищем его в боевом коде.
"""
import io
import os
import re

КОРЕНЬ = r"C:\sender\sender"
ИСКАТЬ = ("'отказ'", '"отказ"', "'автоответ'", '"автоответ"',
          "'avtootvet'", '"avtootvet"', "'v_otpuske'", '"v_otpuske"',
          "reply_kind=", "reply_kind =")

for корень, _, файлы in os.walk(КОРЕНЬ):
    if any(ч in корень for ч in ("tests", "__pycache__", ".bak", "web")):
        continue
    for имя in файлы:
        if not имя.endswith(".py") or ".bak" in имя:
            continue
        путь = os.path.join(корень, имя)
        try:
            т = io.open(путь, encoding="utf-8").read()
        except Exception:  # noqa: BLE001
            continue
        строки = т.split("\n")
        for н, строка in enumerate(строки, 1):
            if any(и in строка for и in ИСКАТЬ):
                print("%-42s %-5d %s"
                      % (путь.replace(КОРЕНЬ + "\\", ""), н, строка.strip()[:110]))
