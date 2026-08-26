# -*- coding: utf-8 -*-
"""Снять пометку «не наш ни одному» со всех, кому её поставил предпросев.

ЗАЧЕМ. Владелец 26.08 поймал две ошибки подряд: золотодобыче нужен
компрессор (флотация, дробление, пневмоинструмент), а поставщика овощей
для HoReCa стоит проверить — там мойка, калибровка и фасовка. Разбор
подтвердил: вердикт «никуда» доставался и заводам («Производство и продажа
медицинской мебели» назвали чистой торговлей), и производителю грохотов, и
фасовщику специй.

Ошибка «сняли живую цель» стоит сделки, ошибка «написали лишнему» стоит
трети доллара. Поэтому откатываем ВСЕ пометки и пересуживаем по
исправленным правилам, а не выборочно чиним найденные.

    python vernut_snyatyh.py            # посчитать
    python vernut_snyatyh.py primenit   # снять пометки
"""
import json
import sqlite3
import sys
import time

ДЕЛАТЬ = "primenit" in sys.argv[1:]
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT id, company_name, extra_json FROM recipients "
    " WHERE extra_json LIKE '%ne_nash_ni_odnomu%'").fetchall()
print("с пометкой «не наш ни одному»: %d" % len(ряды))
for r in ряды[:5]:
    print("   %s" % str(r["company_name"])[:60])
if not ДЕЛАТЬ:
    print("\nвхолостую. Снять пометки — primenit")
    raise SystemExit(0)

сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
снято = 0
for r in ряды:
    try:
        extra = json.loads(r["extra_json"] or "{}")
    except Exception:                                         # noqa: BLE001
        continue
    if "ne_nash_ni_odnomu" not in extra:
        continue
    # След оставляем: видно, что пометка была и почему её сняли.
    extra["predprosev_otkat_26_08"] = str(extra.pop("ne_nash_ni_odnomu"))[:200]
    c.execute("UPDATE recipients SET extra_json=?, updated_at=? WHERE id=?",
              (json.dumps(extra, ensure_ascii=False), сейчас, r["id"]))
    снято += 1
c.commit()
c.close()
print("\nпометок снято: %d" % снято)
