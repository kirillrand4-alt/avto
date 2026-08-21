# -*- coding: utf-8 -*-
"""Сколько сейчас времени у нас и у получателей ждущих писем.

Окно отправки задано в часах ПО ЗОНЕ ПОЛУЧАТЕЛЯ. Расширить день мало -
если часы уже прошли, письма всё равно не уйдут. Смотрим, у скольких
адресатов сейчас попадает в 09:00-15:00 и что будет при других границах.
"""
import sys
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, r"C:\sender")
from sender.auto_send import recipient_tz_name, window_from             # noqa: E402
from sender.config import Config                                        # noqa: E402
from sender.store import Store                                          # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
мск = сейчас.astimezone(ZoneInfo("Europe/Moscow"))
print(f"UTC:    {сейчас.strftime('%Y-%m-%d %H:%M')} ({сейчас.strftime('%A')})")
print(f"Москва: {мск.strftime('%Y-%m-%d %H:%M')}")
print(f"окно: {окно.get('start')}-{окно.get('end')}, дни {окно.get('days')}, "
      f"по зоне получателя={окно.get('by_recipient_tz')}")

with store._lock:
    строки = store._conn.execute(
        "SELECT m.recipient_id FROM messages m "
        "  JOIN confirm_reviews cr ON cr.message_id=m.id "
        " WHERE m.status IN ('scheduled','sending') "
        "   AND cr.status IN ('approved','edited')").fetchall()
часы = Counter()
for (rid,) in строки:
    rec = store.get_recipient(int(rid)) if rid else None
    имя = recipient_tz_name(окно, rec) if rec else None
    try:
        ч = сейчас.astimezone(ZoneInfo(имя)).hour if имя else мск.hour
    except Exception:                                                # noqa: BLE001
        ч = мск.hour
    часы[ч] += 1
print(f"\nписем ждёт: {len(строки)}")
print("сейчас у получателей местное время:")
for ч in sorted(часы):
    print(f"   {ч:02d}:xx — {часы[ч]:>4} писем")
for конец in ("15:00", "18:00", "21:00", "23:59"):
    гк = int(конец.split(":")[0])
    влезет = sum(н for ч, н in часы.items() if 9 <= ч < гк)
    print(f"если окно 09:00-{конец}: уйдёт прямо сейчас {влезет} из {len(строки)}")
