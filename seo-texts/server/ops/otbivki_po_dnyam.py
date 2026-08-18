# -*- coding: utf-8 -*-
"""Отбивки по дням: правда ли сегодня их стало меньше — и почему.

Владелец 18.08: «сейчас сильно упали отбивки на сегодняшней отправке».
Проверяем числом и сразу отвечаем на главный вопрос: доля упала потому, что
письма стали лучше отобраны, — или потому, что сегодняшняя партия просто
состоит из адресов, которые проба подтвердила?

Отбивка отбивке рознь: hard — ящика нет (репутационный урон), policy —
письмо завернули, ящик живой. Гейт репутации считает обе, поэтому печатаем
раздельно.

    python zapusk_svoego_skripta.py ops/otbivki_po_dnyam.py
"""
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    отправки = store._conn.execute(
        "SELECT substr(event_ts,1,10) d, COUNT(*) FROM events "
        "WHERE event_type='sent' GROUP BY d ORDER BY d").fetchall()
    отбивки = store._conn.execute(
        "SELECT substr(e.event_ts,1,10) d, e.detail_json, "
        "       lower(COALESCE(r.email,'')) "
        "FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
        "WHERE e.event_type='bounce' ORDER BY d").fetchall()

по_дням = defaultdict(lambda: {"hard": 0, "policy": 0, "прочие": 0})
for d, dj, email in отбивки:
    try:
        в = str((json.loads(dj or "{}").get("dsn") or {}).get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        в = ""
    ключ = в if в in ("hard", "policy") else "прочие"
    по_дням[d][ключ] += 1

print(f"{'день':<12} {'отправлено':>10} {'hard':>6} {'policy':>7} "
      f"{'прочие':>7} {'доля hard':>10}")
for d, n in отправки[-14:]:
    б = по_дням.get(d, {"hard": 0, "policy": 0, "прочие": 0})
    доля = 100.0 * б["hard"] / n if n else 0.0
    print(f"{d:<12} {n:>10} {б['hard']:>6} {б['policy']:>7} "
          f"{б['прочие']:>7} {доля:>9.1f}%")

# Отбивка приходит не в тот же миг, что отправка. Смотрим ещё и «по письму»:
# для сегодняшних отправок — сколько из них уже вернулось.
сегодня = отправки[-1][0] if отправки else ""
print(f"\n=== сегодняшняя отправка ({сегодня}) по составу адресов")
with store._lock:
    ряд = store._conn.execute(
        "SELECT lower(r.email), e.mailbox_id, COALESCE(p.verdict,'(без пробы)') "
        "FROM events e JOIN recipients r ON r.id=e.recipient_id "
        "LEFT JOIN addr_probe p ON p.email=lower(r.email) "
        "WHERE e.event_type='sent' AND substr(e.event_ts,1,10)=?",
        (сегодня,)).fetchall()
состав = Counter(в for _e, _m, в in ряд)
отбилось_сегодня = {e for _d, _dj, e in отбивки if _d == сегодня}
print(f"писем отправлено: {len(ряд)}")
for в, n in состав.most_common():
    вернулось = sum(1 for e, _m, вв in ряд if вв == в and e in отбилось_сегодня)
    print(f"  {в:<20} {n:>4}   из них уже отбилось: {вернулось}")

по_ящикам = Counter(m for _e, m, _в in ряд)
print("\nпо ящикам сегодня:")
for m, n in по_ящикам.most_common():
    print(f"  {str(m):<40} {n}")
