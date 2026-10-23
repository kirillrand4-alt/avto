# -*- coding: utf-8 -*-
"""Разнос писем ВНУТРИ прохода автоотправки (владелец 23.10: «посмотри, что
письма реально отправляются с рандомной задержкой, а не в одно время»).

Замер 23.10 (pauzy_otpravki.py): у каждого ящика паузы уже случайные
(2-17 мин), но проход отправщика шлёт свою партию (до 4 писем на направление)
подряд — до 8 писем в одну секунду с разных ящиков, 84 таких секунды за утро.
Стало: после каждого отправленного письма проход ждёт случайные 8-25 с и
берёт свежее «сейчас». Проход длиннее, но писем столько же: следующий
начнётся сразу за ним. Остановка службы прерывает ожидание сразу.

Правка по якорю, бэкап .bak-raznos-<время>, py_compile, откат; --otkat.
Нужен Restart-Service SenderPanel -Force.
    raznos_v_prohode.py [--primenit | --otkat] [--koren=<папка>]"""
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
    ("import logging\nimport threading\n", "import logging\nimport random\nimport threading\n"),
    ('''                if out["sent"] > было:
                    по_напр[нап] = по_напр.get(нап, 0) + 1
''', '''                if out["sent"] > было:
                    по_напр[нап] = по_напр.get(нап, 0) + 1
                    # РАЗНОС-23.10 (владелец: «чтобы письма реально уходили с
                    # рандомной задержкой, а не в одно время»): партия прохода
                    # шла подряд — до 8 писем в одну секунду с разных ящиков.
                    # Теперь между отправками случайные 8-25 с; стоп службы
                    # прерывает ожидание.
                    if self._stop.wait(random.uniform(8, 25)):
                        break
                    now = datetime.now(timezone.utc)
'''),
]
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-raznos-*"))
    if б:
        shutil.copy2(б[-1], П)
    print("=== РАЗНОС: ОТКАТ (нужен рестарт) ===")
    sys.exit(0)
т = io.open(П, encoding="utf-8").read()
if "РАЗНОС-23.10" in т:
    print("=== РАЗНОС: УЖЕ БЫЛО ===")
    sys.exit(0)
for было, _ in ПАРЫ:
    if т.count(было) != 1:
        print("якорь найден %d раз: %r" % (т.count(было), было[:80]))
        print("=== РАЗНОС: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
for было, стало in ПАРЫ:
    т = т.replace(было, стало)
if "--primenit" not in sys.argv:
    print("якоря на месте, сухой прогон. Применить — --primenit")
    sys.exit(0)
бэкап = П + ".bak-raznos-%d" % int(time.time())
shutil.copy2(П, бэкап)
io.open(П, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(П, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, П)
    print("сбой, откат:", е)
    sys.exit(0)
print("бэкап:", бэкап)
print("=== РАЗНОС: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
