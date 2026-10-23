# -*- coding: utf-8 -*-
"""Темп автоотправки после разноса (владелец 23.10: «давай»): пауза между
письмами прохода 5-15 с вместо 8-25 (около 360 писем в час потолком), лимит
«4 на направление за проход» снят — у КЦ и Meyer снова по batch (10) своих.
Правка по якорям поверх raznos_v_prohode.py и napravleniya_auto_send.py;
бэкап .bak-temp-<время>, py_compile, откат; --otkat. Нужен рестарт.
    raznos_temp.py [--primenit | --otkat] [--koren=<папка>]"""
import glob
import io
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--koren=")), r"C:\sender\sender")
П = os.path.join(КОРЕНЬ, "auto_send.py")
ПАРЫ = [
    ("""        # 22.10 владелец: не залпом — в проходе не больше 4 писем на направление.
        на_напр = min(self.batch, 4)""",
     """        # 22.10 владелец: не залпом — в проходе не больше 4 писем на направление.
        # ТЕМП-23.10: лимит 4 снят («давай» на 5-15 с между письмами) — залпы
        # теперь гасит пауза между письмами прохода, у направления своя партия.
        на_напр = self.batch"""),
    ("""                    if self._stop.wait(random.uniform(8, 25)):""",
     """                    if self._stop.wait(random.uniform(5, 15)):   # ТЕМП-23.10: было 8-25"""),
]
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-temp-*"))
    if б:
        shutil.copy2(б[-1], П)
    print("=== ТЕМП: ОТКАТ (нужен рестарт) ===")
    sys.exit(0)
т = io.open(П, encoding="utf-8").read()
if "ТЕМП-23.10" in т:
    print("=== ТЕМП: УЖЕ БЫЛО ===")
    sys.exit(0)
for было, _ in ПАРЫ:
    if т.count(было) != 1:
        print("якорь найден %d раз: %r" % (т.count(было), было[:80]))
        print("=== ТЕМП: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
for было, стало in ПАРЫ:
    т = т.replace(было, стало)
if "--primenit" not in sys.argv:
    print("якоря на месте, сухой прогон. Применить — --primenit")
    sys.exit(0)
бэкап = П + ".bak-temp-%d" % int(time.time())
shutil.copy2(П, бэкап)
io.open(П, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(П, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, П)
    print("сбой, откат:", е)
    sys.exit(0)
print("бэкап:", бэкап)
print("=== ТЕМП: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
