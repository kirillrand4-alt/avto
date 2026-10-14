# -*- coding: utf-8 -*-
"""confirm.py: заслон «сделка в работе» по направлениям (владелец 14.10). Правка по якорю, бэкап, py_compile, откат."""
import io
import py_compile
import shutil
import sys
import time
ПУТЬ = r"C:\\sender\\sender\\confirm.py"
т = io.open(ПУТЬ, encoding="utf-8").read()
if "СДЕЛКА В РАБОТЕ ПО НАПРАВЛЕНИЮ — ПЕРВОЙ" in т:
    print("=== СДЕЛКИ: CONFIRM ПЕРВОЙ: УЖЕ БЫЛО ===")
    sys.exit(0)
ПАРЫ = [('        """Красные стоп-флаги направления для панели; [] если гейт неактивен/ок."""\n        cards = self._cards\n', '        """Красные стоп-флаги направления для панели; [] если гейт неактивен/ок."""\n        # СДЕЛКА В РАБОТЕ ПО НАПРАВЛЕНИЮ — ПЕРВОЙ (владелец 14.10): до развилки\n        # «вне базы обзвона», иначе жёлтый флаг вне-базы её заслонял.\n        if campaign_id:\n            try:\n                from sender.company_card import campaign_division as _cdiv\n                from sender.sdelki_napr import blok as _sdelka\n                _camp = self._store.get_campaign(campaign_id)\n                _cd = _cdiv(_camp) if _camp else None\n                if _cd:\n                    with self._store._lock:\n                        _сд = _sdelka(self._store._conn, inn, _cd)\n                    if _сд:\n                        return [{"code": "deal_in_division", "severity": "red",\n                                 "label": "СДЕЛКА В РАБОТЕ: " + _сд}]\n            except Exception:  # noqa: BLE001 - заслон не роняет очередь\n                pass\n        cards = self._cards\n')]
for с, _н in ПАРЫ:
    if т.count(с) != 1:
        print("якорь (%d): %r" % (т.count(с), с[:120]))
        print("=== СДЕЛКИ: CONFIRM ПЕРВОЙ: НЕ ПРИМЕНЕНО ===")
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
    print("=== СДЕЛКИ: CONFIRM ПЕРВОЙ: ОТКАТ ===")
    sys.exit(0)
print("бэкап: %s" % бэкап)
print("=== СДЕЛКИ: CONFIRM ПЕРВОЙ: ПРИМЕНЕНО ===")
