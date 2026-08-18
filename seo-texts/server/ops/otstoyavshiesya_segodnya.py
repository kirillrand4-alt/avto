# -*- coding: utf-8 -*-
"""Доля отбивок ТОЛЬКО по письмам, которые успели «отстояться».

Отбивка возвращается быстро: медиана 8 минут, три четверти — за 14. Значит
письмо старше 20 минут уже почти наверняка сказало о себе всё, а свежее ещё
молчит и разбавляет долю. Считаем раздельно.

    python zapusk_svoego_skripta.py ops/otstoyavshiesya_segodnya.py [минут]
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ОКНО = int(sys.argv[1]) if len(sys.argv) > 1 else 20
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)
рубеж = (сейчас - timedelta(minutes=ОКНО)).isoformat()
сегодня = сейчас.strftime("%Y-%m-%d")

with store._lock:
    отстоялись = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='sent' "
        "AND substr(event_ts,1,10)=? AND event_ts<?",
        (сегодня, рубеж)).fetchone()[0]
    свежие = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='sent' "
        "AND substr(event_ts,1,10)=? AND event_ts>=?",
        (сегодня, рубеж)).fetchone()[0]
    отбилось = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='bounce' "
        "AND substr(event_ts,1,10)=?", (сегодня,)).fetchone()[0]
    # Отбивки по письмам из «отстоявшейся» части: получатель тот же.
    отб_отстоявшихся = store._conn.execute(
        "SELECT COUNT(DISTINCT b.recipient_id) FROM events b "
        "JOIN events s ON s.recipient_id=b.recipient_id AND s.event_type='sent' "
        "AND substr(s.event_ts,1,10)=? AND s.event_ts<? "
        "WHERE b.event_type='bounce' AND substr(b.event_ts,1,10)=?",
        (сегодня, рубеж, сегодня)).fetchone()[0]

доля_всё = 100.0 * отбилось / (отстоялись + свежие) if (отстоялись + свежие) else 0
доля_отст = 100.0 * отб_отстоявшихся / отстоялись if отстоялись else 0
print(f"сейчас {сейчас.strftime('%H:%M')} UTC, окно ожидания {ОКНО} мин\n")
print(f"отправлено сегодня всего:      {отстоялись + свежие}")
print(f"  из них успели отстояться:    {отстоялись}")
print(f"  ушли только что (ещё молчат):{свежие}")
print(f"отбивок сегодня:               {отбилось}")
print(f"\nдоля «в лоб» (по всему дню):        {доля_всё:.1f}%")
print(f"доля по отстоявшимся письмам:       {доля_отст:.1f}%  "
      f"({отб_отстоявшихся} из {отстоялись})")
print("\nвторая цифра честнее: свежие письма долю занижают, "
      "они ещё не успели отбиться.")
