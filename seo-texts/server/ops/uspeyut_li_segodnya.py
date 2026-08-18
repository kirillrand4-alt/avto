# -*- coding: utf-8 -*-
"""Сколько оставшихся писем ещё успевает в своё окно СЕГОДНЯ.

Окно отправки считается по времени ПОЛУЧАТЕЛЯ (09:00-12:00 у него дома).
Поэтому лимиты - только половина ответа: у части адресов окно уже закрылось,
и никакой потолок их сегодня не выпустит. Считаем по часовым поясам.

    python zapusk_svoego_skripta.py ops/uspeyut_li_segodnya.py
"""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
окно = store.get_setting("sending_window") or {}
НАЧ = int(str(окно.get("start", "09:00")).split(":")[0])
КОН = int(str(окно.get("end", "12:00")).split(":")[0])
сейчас = datetime.now(timezone.utc)
print(f"окно у получателя: {НАЧ}:00-{КОН}:00, сейчас {сейчас.strftime('%H:%M')} UTC\n")

with store._lock:
    ряд = store._conn.execute(
        "SELECT COALESCE(r.tz,''), COALESCE(r.mx_provider,'unknown'), COUNT(*) "
        "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='approved' GROUP BY 1,2").fetchall()

маршрут = cfg.get("provider_split.routing", {}) or {}
итог = Counter()
подробно = []
for tz, пров, n in ряд:
    try:
        from zoneinfo import ZoneInfo
        мест = сейчас.astimezone(ZoneInfo(tz)) if tz else None
    except Exception:                                            # noqa: BLE001
        мест = None
    if мест is None:
        состояние = "часовой пояс неизвестен"
    elif мест.hour < НАЧ:
        состояние = "окно ещё впереди"
    elif мест.hour < КОН:
        состояние = "окно ОТКРЫТО сейчас"
    else:
        состояние = "окно уже закрылось"
    пул = маршрут.get(str(пров).lower()) or маршрут.get("other") or "?"
    итог[(состояние, пул)] += n
    подробно.append((tz, мест.strftime("%H:%M") if мест else "-", пров, пул, n,
                     состояние))

print(f"{'пояс':<22} {'местное':>8} {'пул':<14} {'писем':>6}  состояние")
for tz, мест, пров, пул, n, сост in sorted(подробно, key=lambda x: -x[4])[:25]:
    print(f"  {str(tz or '(пусто)'):<20} {мест:>8} {пул:<14} {n:>6}  {сост}")

print("\nсводно:")
for (сост, пул), n in sorted(итог.items(), key=lambda x: -x[1]):
    print(f"  {сост:<24} {пул:<14} {n}")
