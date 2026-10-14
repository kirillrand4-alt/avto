# -*- coding: utf-8 -*-
"""confirm.py: запрет по активной сделке направления — без обхода «Отправить всё равно» (владелец 14.10)."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "АКТИВНАЯ СДЕЛКА НАПРАВЛЕНИЯ — БЕЗ ОБХОДА" in т:
    print("=== СДЕЛКА БЕЗ ОБХОДА: CONFIRM: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('            div_blocked = self._division_blocked(row)\n', '            div_blocked = self._division_blocked(row)\n            # АКТИВНАЯ СДЕЛКА НАПРАВЛЕНИЯ — БЕЗ ОБХОДА (владелец 14.10: «запрет\n            # в панели на отправку»). «Отправить всё равно» её не снимает.\n            if div_blocked and str(div_blocked).startswith("СДЕЛКА В РАБОТЕ"):\n                raise ConfirmBlockedError(\n                    f"отправка запрещена ({div_blocked}) — обхода нет")\n')]
for с, _н in ПАРЫ:
    if т.count(с) != 2:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== СДЕЛКА БЕЗ ОБХОДА: CONFIRM: НЕ ПРИМЕНЕНО ===")
        sys.exit(0)
бэкап = ПУТЬ + ".bak-%d" % int(time.time())
shutil.copy2(ПУТЬ, бэкап)
for с, н in ПАРЫ:
    т = т.replace(с, н)
io.open(ПУТЬ, "w", encoding="utf-8").write(т)
try:
    py_compile.compile(ПУТЬ, doraise=True)
except Exception as е:  # noqa: BLE001
    shutil.copy2(бэкап, ПУТЬ)
    print("сбой, откат: %s" % е)
    print("=== СДЕЛКА БЕЗ ОБХОДА: CONFIRM: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== СДЕЛКА БЕЗ ОБХОДА: CONFIRM: ПРИМЕНЕНО ===")
