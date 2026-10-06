# -*- coding: utf-8 -*-
"""Какие роли реально есть в базе и сколько баллов им даёт скоринг.

Владелец: «директор — это не ЛПР, ЛПР это инженеры в первую очередь».
Смотрим, что на самом деле стоит в весах и какие роли в базе остались
без веса вовсе.
"""
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")

_ROLE_PTS = {'снабжение/закупки': 15, 'гл.инженер': 13, 'директор': 12,
             'продажи': 8, 'общий': 5, 'приёмная': 4, 'бухгалтерия': 2,
             'кадры': 2}
try:
    from lead_scoring import _ROLE_PTS as ЖИВЫЕ                 # noqa: E402
    _ROLE_PTS = dict(ЖИВЫЕ)
    откуда = "прочитано из lead_scoring.py на сервере"
except Exception as ex:                                         # noqa: BLE001
    откуда = "скопировано из репозитория (%s)" % str(ex)[:50]

cx = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True)
cx.row_factory = sqlite3.Row
print("веса ролей: %s" % откуда)
print("")
print("   %-24s %7s %7s" % ("роль в базе", "адресов", "баллов"))
без_веса = 0
for р in cx.execute("SELECT COALESCE(NULLIF(role,''),'(пусто)') r, COUNT(*) n "
                    "  FROM emails GROUP BY 1 ORDER BY 2 DESC LIMIT 25"):
    роль, n = str(р["r"]), int(р["n"])
    балл = _ROLE_PTS.get(роль)
    метка = "%7d" % балл if балл is not None else "      0  ← веса НЕТ"
    if балл is None and роль != "(пусто)":
        без_веса += n
    print("   %-24s %7d %s" % (роль[:24], n, метка))

print("")
print("--- адресов с ролью, которой нет в таблице весов: %d ---" % без_веса)
print("")
print("--- таблица весов целиком ---")
for к, в in sorted(_ROLE_PTS.items(), key=lambda x: -x[1]):
    print("   %-24s %3d" % (к, в))
cx.close()
print("")
print("=" * 74)
print("=== РОЛИ И БАЛЛЫ ===")
