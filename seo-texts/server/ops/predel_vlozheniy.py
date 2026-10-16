# -*- coding: utf-8 -*-
"""Предел вложения в панели 15 -> 20 МБ, на письмо 20 -> 25 МБ (владелец 16.10:
презентация 15,3 МБ не прикреплялась). Правка api/app.py по якорям, бэкап .bak-predel-*.
Нужен Restart-Service SenderPanel -Force."""
import io, py_compile, shutil, sys, time
П = r"C:\sender\sender\api\app.py"
т = io.open(П, encoding="utf-8").read()
ПАРЫ = [("ПРЕДЕЛ_ФАЙЛА = 15 * 1024 * 1024          # 15 МБ: больше почта режет сама",
         "ПРЕДЕЛ_ФАЙЛА = 20 * 1024 * 1024          # 20 МБ (владелец 16.10: презентации); base64 ~27 МБ, Яндекс берёт до 30"),
        ("ПРЕДЕЛ_ПИСЬМА = 20 * 1024 * 1024", "ПРЕДЕЛ_ПИСЬМА = 25 * 1024 * 1024")]
if "ПРЕДЕЛ_ФАЙЛА = 20 * 1024" in т:
    print("=== ПРЕДЕЛ: УЖЕ БЫЛО ==="); sys.exit()
for с, _ in ПАРЫ:
    if т.count(с) != 1:
        print("якорь:", т.count(с), с[:50]); print("=== ПРЕДЕЛ: НЕ ПРИМЕНЕНО ==="); sys.exit()
б = П + ".bak-predel-%d" % int(time.time()); shutil.copy2(П, б)
for с, н in ПАРЫ: т = т.replace(с, н)
io.open(П, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(П, doraise=True)
except Exception as е:
    shutil.copy2(б, П); print("откат:", е); sys.exit()
print("бэкап:", б); print("=== ПРЕДЕЛ: ПРИМЕНЕНО (нужен перезапуск панели) ===")
