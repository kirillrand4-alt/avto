# -*- coding: utf-8 -*-
"""Пробел в длинной русской теме (владелец 27.10: «почему слитно компрессорамв»).
В базе тема верная («Вопрос по компрессорам в «…»»). Ломает упаковка: SMTP-политика
режет заголовок по 78 знаков, Python кладёт стык кодированных кусков ровно на
пробел, а почтовики пробел между кусками по RFC 2047 выбрасывают —
«компрессорамв», «оборудованиюдля». Заголовки собираем без переноса
(max_line_length=998: тема одним куском); тело это не трогает — его кодировка
уже разложена set_content строками по 76.
Правка по якорю в sender.py: бэкап .bak-tema-<время>, py_compile, откат.
    tema_probel.py [--primenit | --otkat] [--koren=<папка>]"""
import glob
import io
import os
import py_compile
import shutil
import sys
import time

КОРЕНЬ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--koren=")), r"C:\sender\sender")
П = os.path.join(КОРЕНЬ, "sender.py")
БЫЛО = """        from email.policy import SMTP as _SMTP_POLICY
        return msg.as_bytes(policy=_SMTP_POLICY)"""
СТАЛО = """        from email.policy import SMTP as _SMTP_POLICY
        # ТЕМА-ПРОБЕЛ-27.10: без переноса заголовков — иначе стык кодированных
        # кусков темы падает на пробел и почтовик склеивает «компрессорамв».
        return msg.as_bytes(policy=_SMTP_POLICY.clone(max_line_length=998))"""
if "--otkat" in sys.argv:
    б = sorted(glob.glob(П + ".bak-tema-*"))
    if б:
        shutil.copy2(б[-1], П)
    print("=== ТЕМА: ОТКАТ (нужен рестарт) ===")
    sys.exit(0)
т = io.open(П, encoding="utf-8").read()
if "ТЕМА-ПРОБЕЛ-27.10" in т:
    print("=== ТЕМА: УЖЕ БЫЛО ===")
    sys.exit(0)
if т.count(БЫЛО) != 1:
    print("якорь найден %d раз" % т.count(БЫЛО))
    print("=== ТЕМА: НЕ ПРИМЕНЕНО ===")
    sys.exit(0)
т = т.replace(БЫЛО, СТАЛО)
if "--primenit" not in sys.argv:
    print("якорь на месте, сухой прогон. Применить — --primenit")
    sys.exit(0)
бэкап = П + ".bak-tema-%d" % int(time.time())
shutil.copy2(П, бэкап)
io.open(П, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(П, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, П)
    print("сбой, откат:", е)
    sys.exit(0)
print("бэкап:", бэкап)
print("=== ТЕМА: ПРИМЕНЕНО (нужен Restart-Service SenderPanel -Force) ===")
