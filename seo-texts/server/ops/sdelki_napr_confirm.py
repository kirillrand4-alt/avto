# -*- coding: utf-8 -*-
"""confirm.py: заслон «сделка в работе» по направлениям (владелец 14.10). Правка по якорю, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "deal_in_division" in т:
    print("=== СДЕЛКИ: CONFIRM: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('        if camp_div is not None and allowed and camp_div not in allowed:', '        # СДЕЛКА В РАБОТЕ ПО НАПРАВЛЕНИЮ (владелец 14.10): сделка Meyer — не\n        # пишет Meyer, сделка КЦ — не пишет КЦ, только СЦ — пишут все.\n        if camp_div:\n            try:\n                from sender.sdelki_napr import blok as _sdelka\n                with self._store._lock:\n                    _сд = _sdelka(self._store._conn, inn, camp_div)\n                if _сд:\n                    return [{"code": "deal_in_division", "severity": "red",\n                             "label": "СДЕЛКА В РАБОТЕ: " + _сд}]\n            except Exception:  # noqa: BLE001 - заслон не роняет очередь\n                pass\n        if camp_div is not None and allowed and camp_div not in allowed:')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== СДЕЛКИ: CONFIRM: НЕ ПРИМЕНЕНО ===")
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
    print("=== СДЕЛКИ: CONFIRM: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== СДЕЛКИ: CONFIRM: ПРИМЕНЕНО ===")
