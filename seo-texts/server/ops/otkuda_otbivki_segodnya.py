# -*- coding: utf-8 -*-
"""Откуда сегодняшние отбивки: адреса, диагностика, ящик, письмо.

Владелец: «три штуки за сегодня - в пять раз выше вчерашней нормы». Три
события на трёхстах письмах это ещё не тренд, но разобрать надо каждое:
жёсткая отбивка (ящика нет) и отказ по политике - разные болезни, и лечатся
по-разному.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряды = store._conn.execute(
        """SELECT e.created_at, e.event_type, COALESCE(r.email,''),
                  COALESCE(rc.company_name,''), COALESCE(e.detail_json,''),
                  COALESCE(e.mailbox_id, m.mailbox_id, ''), COALESCE(rc.mx_provider,'')
             FROM events e
             LEFT JOIN messages m ON m.id=e.message_id
             LEFT JOIN recipients r ON r.id=e.recipient_id
             LEFT JOIN recipients rc ON rc.id=e.recipient_id
            WHERE e.event_type IN ('bounce','dsn')
              AND date(e.created_at) >= date('now','-2 day')
            ORDER BY e.created_at""").fetchall()

по_дням = Counter()
print(f"событий отбивки за два дня: {len(ряды)}\n")
for ts, тип, email, имя, dj, ящик, mx in ряды:
    по_дням[str(ts)[:10]] += 1
    try:
        d = json.loads(dj or "{}")
    except Exception:                                            # noqa: BLE001
        d = {}
    dsn = d.get("dsn") or {}
    вердикт = str(dsn.get("verdict") or d.get("verdict") or "?")
    диаг = str(dsn.get("diagnostic") or d.get("diagnostic")
               or d.get("reason") or "")[:150]
    код = str(dsn.get("status") or dsn.get("code") or "")
    print(f"{str(ts)[:19]}  {тип}  {вердикт:<10} {email}")
    print(f"    фирма: {имя[:46]}  почтовик: {mx}")
    print(f"    ящик:  {ящик}")
    print(f"    код {код}: {диаг}")
print("\nпо дням:", dict(по_дням))

# сколько всего ушло в эти дни - без знаменателя доля не считается
with store._lock:
    отпр = store._conn.execute(
        "SELECT date(sent_at), COUNT(*) FROM messages WHERE status='sent' "
        "AND date(sent_at) >= date('now','-2 day') GROUP BY 1").fetchall()
print("отправлено по дням:", {d: n for d, n in отпр})
for д, n in отпр:
    б = по_дням.get(д, 0)
    print(f"  {д}: {б} отбивок на {n} писем = {100.0 * б / max(1, n):.2f}%")
