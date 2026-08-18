# -*- coding: utf-8 -*-
"""Успела ли сегодняшняя отправка «отстояться»: лаг между письмом и отбивкой.

Низкая доля отбивок за сегодня значит одно, если письма ушли пять часов
назад, и совсем другое, если половина ушла двадцать минут назад. Считаем по
истории, сколько времени проходит от отправки до отбивки, и смотрим, сколько
сегодняшних писем этот срок уже пережило.

    python zapusk_svoego_skripta.py ops/otbivka_zapazdyvanie.py
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)


def _ч(ts):
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:                                            # noqa: BLE001
        return None


# 1. Исторический лаг: отправка -> отбивка по одному и тому же получателю.
with store._lock:
    пары = store._conn.execute(
        "SELECT s.recipient_id, MIN(s.event_ts), MIN(b.event_ts) FROM events s "
        "JOIN events b ON b.recipient_id=s.recipient_id AND b.event_type='bounce' "
        "WHERE s.event_type='sent' GROUP BY s.recipient_id").fetchall()
лаги = []
for _rid, ts_s, ts_b in пары:
    a, b = _ч(ts_s), _ч(ts_b)
    if a and b and b >= a:
        лаги.append((b - a).total_seconds() / 60.0)
лаги.sort()
if лаги:
    def кв(p):
        return лаги[min(len(лаги) - 1, int(len(лаги) * p))]
    print(f"лаг «отправлено -> отбилось» по {len(лаги)} случаям, минут: "
          f"медиана {кв(0.5):.0f} | 75% {кв(0.75):.0f} | 90% {кв(0.9):.0f} | "
          f"максимум {лаги[-1]:.0f}")
else:
    print("исторических пар нет")

# 2. Сегодняшняя отправка по часам и сколько ей уже «отстоялось».
сегодня = сейчас.strftime("%Y-%m-%d")
with store._lock:
    ряд = store._conn.execute(
        "SELECT event_ts FROM events WHERE event_type='sent' "
        "AND substr(event_ts,1,10)=?", (сегодня,)).fetchall()
по_часам = Counter()
свежие = 0
порог = кв(0.9) if лаги else 60.0
for (ts,) in ряд:
    d = _ч(ts)
    if not d:
        continue
    по_часам[d.strftime("%H")] += 1
    if (сейчас - d).total_seconds() / 60.0 < порог:
        свежие += 1
print(f"\nсегодня отправлено {len(ряд)} писем, по часам UTC:")
for ч in sorted(по_часам):
    мск = (int(ч) + 3) % 24
    print(f"  {ч}:00 UTC ({мск:02d}:00 МСК)  {по_часам[ч]}")
print(f"\nсейчас {сейчас.strftime('%H:%M')} UTC. Не «отстоялось» "
      f"{порог:.0f} минут у {свежие} писем из {len(ряд)} — по ним отбивка "
      f"ещё может прийти.")

# 3. Сегодняшние отбивки по часам.
with store._lock:
    б = store._conn.execute(
        "SELECT event_ts FROM events WHERE event_type='bounce' "
        "AND substr(event_ts,1,10)=?", (сегодня,)).fetchall()
print(f"\nсегодняшние отбивки ({len(б)}):")
for (ts,) in б:
    print(f"  {str(ts)[:19]}")
