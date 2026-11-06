# -*- coding: utf-8 -*-
"""Повтор на тот же адрес без ответа: 30 -> 15 дней (владелец 06.11 «давай 15 дней»,
«главное чтобы они нам уже не отвечали»). Две правки по якорям: confirm.py (ручное
подтверждение) и auto_send.py (автоотправка). Проверка «не отвечали» не трогается.
Бэкап .bak-povtor15-<время>, py_compile, откат.  [--primenit | --otkat]"""
import glob, io, os, py_compile, shutil, sys, time
К = r"C:\sender\sender"
ПРАВКИ = [("confirm.py", "    _ПОВТОР_ДНЕЙ = 30\n", "    _ПОВТОР_ДНЕЙ = 15   # владелец 06.11: было 30\n"),
          ("auto_send.py", "if _когда_а is not None and now - _когда_а >= timedelta(days=30):",
           "if _когда_а is not None and now - _когда_а >= timedelta(days=15):   # владелец 06.11: было 30")]
if "--otkat" in sys.argv:
    for ф, _, _ in ПРАВКИ:
        б = sorted(glob.glob(os.path.join(К, ф) + ".bak-povtor15-*"))
        if б: shutil.copy2(б[-1], os.path.join(К, ф))
    print("=== ПОВТОР15: ОТКАТ (нужен рестарт) ==="); sys.exit(0)
тексты = {}
for ф, было, стало in ПРАВКИ:
    т = io.open(os.path.join(К, ф), encoding="utf-8").read()
    if стало in т:
        print(ф, ": уже"); continue
    if т.count(было) != 1:
        print(ф, ": якорь найден %d раз — НЕ ПРИМЕНЕНО" % т.count(было)); sys.exit(0)
    тексты[ф] = т.replace(было, стало)
if "--primenit" not in sys.argv:
    print("якоря на месте:", list(тексты), "— сухой прогон"); sys.exit(0)
t = int(time.time()); бэкапы = []
for ф, т in тексты.items():
    п = os.path.join(К, ф); shutil.copy2(п, п + ".bak-povtor15-%d" % t); бэкапы.append(п)
    io.open(п, "w", encoding="utf-8").write(т)
try:
    for п in бэкапы: py_compile.compile(п, doraise=True)
except Exception as е:  # noqa: BLE001
    for п in бэкапы: shutil.copy2(п + ".bak-povtor15-%d" % t, п)
    print("сбой, откат:", е); sys.exit(0)
print("=== ПОВТОР15: ПРИМЕНЕНО (нужен рестарт) ===")
