# -*- coding: utf-8 -*-
"""Отдать работнику адреса очереди, которых он ни разу не проверял.

Соседний probe_zadanie_gruppy.py отбирает тех, у кого вердикта НЕТ ВОВСЕ
(probe.cached). Нам этого мало: у наших 340 вердикт есть, но он не от
работника — строки с пустым source, которых в его файле нет ни одной
(замер: 13070 таких строк, пересечение с файлом ноль).

Поэтому отбираем по source: всё, что не 'проба', работник не видел.
Отдаём тем же путём, что и панель для срочных — ProbeSync.срочно.

    python otdat_rabotniku_neprovennye.py [сколько]            посчитать
    python otdat_rabotniku_neprovennye.py [сколько] --otpravit отдать
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                   # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.probe_sync import build_probe_sync                   # noqa: E402
from sender.store import Store                                   # noqa: E402

ПРЕДЕЛ = int(next((a for a in sys.argv[1:] if a.isdigit()), "0"))
ОТПРАВИТЬ = "--otpravit" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = build_addr_probe(store, cfg)
цикл = build_probe_sync(store, getattr(проба, "probe_", проба), cfg)

with store._lock:
    ряды = store._conn.execute(
        "SELECT lower(cr.email) e, COALESCE(p.source,'') src, "
        "       COALESCE(p.verdict,'') v "
        "FROM messages m JOIN confirm_reviews cr ON cr.message_id = m.id "
        "LEFT JOIN addr_probe p ON p.email = lower(cr.email) "
        "WHERE cr.status IN ('approved','edited') "
        "AND m.status IN ('scheduled','sending')").fetchall()

счёт = Counter()
надо = []
for r in ряды:
    e = str(r["e"] or "").strip()
    if not e:
        continue
    if str(r["src"]) == "проба":
        счёт["работник уже проверял"] += 1
        continue
    счёт[f"работник не видел (вердикт «{r['v'] or 'нет'}»)"] += 1
    надо.append(e)

надо = sorted(set(надо))
if ПРЕДЕЛ:
    надо = надо[:ПРЕДЕЛ]
print(f"писем в отправке: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
print(f"\nк отправке работнику: {len(надо)}")

if not ОТПРАВИТЬ:
    print("сухой прогон. Отдать — --otpravit")
    raise SystemExit(0)
# ProbeSync.срочно отсеивает всё, у чего вердикт уже есть (probe.cached),
# и на наших 340 отдал ноль: вердикт у них есть, просто не от работника.
# Поэтому делаем ровно то же самое, что делает срочно, минус этот отсев —
# своими руками, не трогая общий код панели. Задание ДОПИСЫВАЕТСЯ, иначе
# наши адреса выбьют с дропа сотни чужих ждущих.
import json                                                      # noqa: E402
from sender.probe_sync import ЗАДАНИЕ                             # noqa: E402

было = []
try:
    сыро = цикл._дроп("GET", ЗАДАНИЕ).decode("utf-8", "replace")
    было = json.loads(сыро)
    if isinstance(было, dict):
        было = было.get("emails") or []
except Exception as ex:                                          # noqa: BLE001
    print("задания на дропе ещё нет:", str(ex)[:80])

список, видели = [], set()
for а in надо + [str(x).strip().lower() for x in (было or [])]:
    if а and а not in видели:
        видели.add(а)
        список.append(а)
цикл._дроп("PUT", ЗАДАНИЕ,
           json.dumps(список, ensure_ascii=False).encode("utf-8"))
print(f"в задании на дропе: {len(список)} адресов "
      f"(было {len(было or [])}, добавил {len(надо)})")
try:
    цикл._толкнуть(len(список))
    print("работник разбужен")
except Exception as ex:                                          # noqa: BLE001
    print("толчок не прошёл (уйдут обычным кругом):", str(ex)[:90])
