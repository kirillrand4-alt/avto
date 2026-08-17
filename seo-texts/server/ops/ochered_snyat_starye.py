# -*- coding: utf-8 -*-
"""Снять из очереди письма, написанные до 10.08.2026 (задание владельца 17.08).

«Очистить все письма, которые были сгенерированы до 10.08.2026, во всех
группах». Письма той эпохи писались по другим правилам: без поля
letter_division, без сверки имени с ящиком, без канонной концовки КЦ, часть
- с направлением, которое спорит с карточкой. Держать их в очереди рядом со
свежими нельзя: оператор подтверждает вперемешку.

ЧТО ИМЕННО ДЕЛАЕМ. Строки НЕ удаляем - переводим в 'skipped'. Причины две:
удаление необратимо и уносит историю (по dedup_key видно, что компании уже
писали), а skipped из очереди оператора убирает ровно так же. Понадобится
вернуть - вернём.

ТРОГАЕМ ТОЛЬКО pending. Отправленные переписывать поздно, а approved ждёт
живой отправки - решение по ним принимал человек.

Без аргумента - только считает (сухой прогон). Снимает при `--снять`.

    python zapusk_svoego_skripta.py ops/ochered_snyat_starye.py
    python zapusk_svoego_skripta.py ops/ochered_snyat_starye.py --снять
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

РУБЕЖ = "2026-08-10"
СНИМАТЬ = "--снять" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    строки = store._conn.execute(
        "SELECT id, status, campaign_id, created_at, kind, email, subject "
        "FROM confirm_reviews ORDER BY id").fetchall()

счёт = Counter()
кандидаты = []
for rid, статус, camp, создано, вид, email, тема in строки:
    счёт["всего строк"] += 1
    когда = str(создано or "")[:10]
    старое = bool(когда) and когда < РУБЕЖ
    счёт[f"{'до' if старое else 'с'} {РУБЕЖ}"] += 1
    if not старое:
        continue
    счёт[f"  старое, статус {статус}"] += 1
    if статус != "pending":
        continue
    if (вид or "outbound") == "reply":
        счёт["  старое pending, но это черновик ответа - не трогаем"] += 1
        continue
    кандидаты.append((rid, camp, когда, email, тема))

print(f"рубеж: письма, созданные РАНЬШЕ {РУБЕЖ}")
for k, n in счёт.most_common():
    print(f"  {k:<44} {n}")
print(f"\nк снятию (pending, не ответы): {len(кандидаты)}")
по_кампаниям = Counter(c for _r, c, _w, _e, _t in кандидаты)
for c, n in по_кампаниям.most_common():
    print(f"  кампания {c}: {n}")
for rid, camp, когда, email, тема in кандидаты[:10]:
    print(f"  #{rid} камп.{camp} {когда} {str(email)[:34]:<36} "
          f"{str(тема)[:44]}")

if not СНИМАТЬ:
    print("\nсухой прогон: ничего не тронуто. Снять - аргумент --снять")
    raise SystemExit(0)

снято = сбоев = 0
for rid, _c, _w, _e, _t in кандидаты:
    try:
        with store._lock:
            store._conn.execute(
                "UPDATE confirm_reviews SET status='skipped', "
                "decided_at=datetime('now'), decided_by='ops:старее-рубежа', "
                "reason=? , updated_at=datetime('now') WHERE id=? "
                "AND status='pending'",
                (f"снято как написанное до {РУБЕЖ}", int(rid)))
            store._conn.commit()
        снято += 1
    except Exception as ex:                                     # noqa: BLE001
        сбоев += 1
        if сбоев <= 5:
            print(f"  #{rid} не снялось: {str(ex)[:110]}")

print(f"\nснято {снято} | сбоев {сбоев}")
with store._lock:
    осталось = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE status='pending'"
    ).fetchone()[0]
print(f"pending в очереди осталось: {осталось}")
