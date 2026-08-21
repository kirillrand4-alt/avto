# -*- coding: utf-8 -*-
"""Завести карточкам вебинара 28.08 свою группу в фильтре очереди.

Панель делит очередь по группам получателя: группа = `segment` ПЛЮС
список `extra_json.gruppy`. Вебинарные получатели заводились без того и
другого, поэтому под любым выбранным фильтром их не видно вовсе.

Пишем в СПИСОК, а не в segment: часть этих компаний уже состоит в
«Партии 935», и перезапись segment выкинула бы их оттуда - ровно та
беда, ради которой список и заведён (заливка металлообработки 05.08).

Без аргумента - сухой прогон. С «primenit» - записывает.
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ГРУППА = "Вебинар 28.08"
писать = len(sys.argv) > 1 and sys.argv[1] == "primenit"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    строки = store._conn.execute(
        "SELECT DISTINCT r.recipient_id, COALESCE(rc.segment,''), "
        "       COALESCE(rc.extra_json,'') "
        "  FROM confirm_reviews r "
        "  JOIN recipients rc ON rc.id = r.recipient_id "
        " WHERE r.dedup_key LIKE 'vebinar28:%'").fetchall()

print(f"получателей вебинара: {len(строки)}")
надо, уже = [], 0
for rid, seg, extra in строки:
    try:
        д = json.loads(extra) if extra else {}
    except Exception:                                         # noqa: BLE001
        д = {}
    гр = list(д.get("gruppy") or [])
    if ГРУППА in гр or seg == ГРУППА:
        уже += 1
        continue
    гр.append(ГРУППА)
    д["gruppy"] = гр
    надо.append((rid, json.dumps(д, ensure_ascii=False)))

print(f"уже в группе: {уже}, дописать: {len(надо)}")
if not писать:
    print("сухой прогон: ничего не менял (запуск с primenit — записать)")
    raise SystemExit(0)
with store._lock:
    for rid, j in надо:
        store._conn.execute(
            "UPDATE recipients SET extra_json=? WHERE id=?", (j, rid))
    store._conn.commit()
print(f"записано: {len(надо)}")
карта = store.recipient_groups() or {}
for г, н in (карта.get("все") or []):
    if "ебинар" in г:
        print(f"в фильтре появилась группа «{г}»: {н} получателей")
