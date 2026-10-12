# -*- coding: utf-8 -*-
"""Поднять лимит анти-штампа «контроль качества» в Meyer-письмах.

Владелец 12.10: «подними лимит и спаси письма в браке». Для рентгена
контроль качества — сама тема письма, а лимит 4 на 49 писем в батче из
четырёх давал ОДНО письмо с этой фразой: 11 из 18 браков партии 500 —
ровно это («контрол\\w* качества (3>1)»). Ставим 37 на 49 — в батче
из четырёх разрешено три.
"""
import io
import os
import py_compile
import shutil
import sys
import time

ПУТЬ = r"C:\sender\sender\ai_letter.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
СТАР = "    r'пищев\\w+ безопасност': 3, r'контрол\\w* качества': 4,\n"
НОВ = ("    r'пищев\\w+ безопасност': 3,\n"
       "    # Для рентгена контроль качества — тема письма, а не штамп (владелец\n"
       "    # 12.10: «подними лимит»). Было 4 на 49: в батче из четырёх писем\n"
       "    # фразу разрешалось одному, и 11 из 18 браков партии 500 — это она.\n"
       "    r'контрол\\w* качества': 37,\n")
if т.count(СТАР) != 1:
    print("якорь не найден (%d) — ничего не трогаю" % т.count(СТАР))
    for с in т.splitlines():
        if "контрол" in с and "качества" in с and ":" in с:
            print("   строка с лимитом: %s" % с.strip()[:100])
    print("=== ЛИМИТ: НЕ ПРИМЕНЁН ===")
    sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
io.open(ПУТЬ, "w", encoding="utf-8").write(т.replace(СТАР, НОВ))
try:
    py_compile.compile(ПУТЬ, doraise=True)
    import importlib.util as _iu
    sys.path.insert(0, r"C:\sender")
    сп = _iu.spec_from_file_location("al_svezh2", ПУТЬ)
    м = _iu.module_from_spec(сп)
    sys.modules["al_svezh2"] = м
    сп.loader.exec_module(м)
    тела = ["контроль качества на линии"] * 3 + ["другое письмо"]
    итог = м.stamp_overflow(тела, "meyer")
    print("проверка: 3 из 4 писем с фразой -> перебор: %r" % итог)
    assert not any("качества" in x for x in итог)
    тела = ["контроль качества"] * 4
    print("проверка: 4 из 4 -> перебор: %r" % м.stamp_overflow(тела, "meyer"))
    print("ЛИМИТ ПОДНЯТ, бэкап %s" % os.path.basename(бэкап))
    print("=== ЛИМИТ: ПРИМЕНЁН ===")
except Exception as e:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("ОТКАТ: %s" % e)
    print("=== ЛИМИТ: ОТКАТ ===")
