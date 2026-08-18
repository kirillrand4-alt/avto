# -*- coding: utf-8 -*-
"""Пошли ли письма после расширения окна: настройка + факт по минутам.

Проверяем ровно две вещи: какое окно стоит сейчас и уходят ли в него письма
тех поясов, что раньше были «за бортом» (Владивосток, Якутск, Красноярск,
Екатеринбург). Настройка без движения в журнале - это ещё не отправка.

    python zapusk_svoego_skripta.py ops/posle_rasshireniya_okna.py
"""
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
сейчас = datetime.now(timezone.utc)

окно = store.get_setting("sending_window")
print(f"окно из панели: {окно}")
w = cfg.sending_window()
print(f"окно из sender.yaml (запасное): дни={w.days} {w.start}-{w.end} {w.tz}")
print(f"сейчас {сейчас.strftime('%H:%M')} UTC / "
      f"{(сейчас + timedelta(hours=3)).strftime('%H:%M')} МСК\n")

# --- отправка по десятиминуткам за последний час --- #
час = (сейчас - timedelta(hours=1)).isoformat()
with store._lock:
    ряд = store._conn.execute(
        "SELECT event_ts, COALESCE(r.tz,'(пусто)') FROM events e "
        "LEFT JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type='sent' AND e.event_ts>? ORDER BY event_ts",
        (час,)).fetchall()
по_десятк = Counter()
for ts, _tz in ряд:
    по_десятк[str(ts)[11:15] + "0"] += 1
print(f"отправлено за последний час: {len(ряд)}")
for к in sorted(по_десятк):
    print(f"  {к} UTC  {'#' * min(60, по_десятк[к])} {по_десятк[к]}")

# --- какие пояса поехали --- #
пояса = Counter(tz for _t, tz in ряд)
print("\nчасовые пояса получателей за этот час:")
for tz, n in пояса.most_common(12):
    try:
        from zoneinfo import ZoneInfo
        мест = сейчас.astimezone(ZoneInfo(tz)).strftime("%H:%M") if tz != "(пусто)" else "-"
    except Exception:                                            # noqa: BLE001
        мест = "?"
    print(f"  {tz:<22} местное {мест:>6}  писем {n}")

# --- что осталось и сколько сейчас «в окне» --- #
with store._lock:
    осталось = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE status='approved'"
    ).fetchone()[0]
    сегодня_всего = store._conn.execute(
        "SELECT COUNT(*) FROM events WHERE event_type='sent' "
        "AND substr(event_ts,1,10)=?", (сейчас.strftime("%Y-%m-%d"),)
    ).fetchone()[0]
print(f"\nотправлено сегодня всего: {сегодня_всего} | осталось готовых: {осталось}")
