# -*- coding: utf-8 -*-
"""Вернуть в очередь коллег, которым лично ещё не писали.

Владелец остановил меня на снятии: «коллегам если не отправляли напиши, но
если им ещё не писали». Я снял пятерых по признаку «писали ранее», а признак
срабатывал по ИНН КОМПАНИИ — то есть писали кому-то в этой фирме, а не этому
человеку. Коллега из автоответа об отпуске — это НОВЫЙ адресат, ему письма
не было.

Разделяем: касание по ЕГО адресу — снимать; касание только по ИНН фирмы —
вернуть в очередь.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАТИТЬ = "--katit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    строки = store._conn.execute(
        "SELECT c.id, c.email, c.reason, r.inn, r.company_name "
        "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='skipped' AND c.reason LIKE '%уже писали%'"
    ).fetchall()
print(f"снятых с причиной «уже писали»: {len(строки)}")

счёт = Counter()
вернуть = []
for r in строки:
    e = str(r["email"] or "").strip().lower()
    ц = "".join(c for c in str(r["inn"] or "") if c.isdigit())
    по_почте = (store.sent_flags(emails=[e]) or {}).get(e) or {}
    по_инн = (store.sent_flags(inns=[ц]) or {}).get(ц) or {} if ц else {}
    if по_почте.get("ever"):
        счёт["писали ЛИЧНО этому адресу — снятие верное"] += 1
        print(f"  #{r['id']} {e}: писали лично "
              f"{str(по_почте.get('last_ts'))[:10]} — оставляю снятым")
    elif по_инн.get("ever"):
        вернуть.append(int(r["id"]))
        счёт["писали только в компанию — ВЕРНУТЬ"] += 1
        print(f"  #{r['id']} {e} ({r['company_name']}): в компанию писали "
              f"{str(по_инн.get('last_ts'))[:10]}, лично — нет -> вернуть")
    else:
        вернуть.append(int(r["id"]))
        счёт["следов нет вовсе — ВЕРНУТЬ"] += 1

print()
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

возвращено = 0
for i in вернуть:
    try:
        with store._lock:
            store._conn.execute(
                "UPDATE confirm_reviews SET status='pending', reason=NULL, "
                "decided_by=NULL, decided_at=NULL, updated_at=datetime('now') "
                "WHERE id=? AND status='skipped'", (i,))
            store._conn.commit()
        возвращено += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{i}: {str(ex)[:90]}")
print(f"\nвернул в очередь: {возвращено}")
