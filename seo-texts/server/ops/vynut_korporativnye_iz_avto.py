# -*- coding: utf-8 -*-
"""Вынуть из автоотправки письма на КОРПОРАТИВНЫЕ почтовые серверы.

Владелец 18.08, увидев отбивку от slenergo.ru: «так у нас же все письма были
не на корпоративных серверах?» - и он прав, дыра есть.

Фильтр «без корпоративных» стоял на ГЕНЕРАЦИИ (ops/partiya_gen.py, argv[4]),
и для писем моего ночного прогона он честно работал. Но письма, написанные
РАНЬШЕ - панельной кнопкой и утренними прогонами, - фильтра не знали, а в
автоотправку я их отбирал по вердикту рецензента, который про почтовые
серверы ничего не знает.

Замер: среди 525 одобренных 26 писем на свои серверы (mx_provider='other'
или пусто). Именно они дают отбивки «550 5.7.1 blocked due to security
reason»: корпоративные шлюзы строги к молодым доменам.

Возвращаем их в pending - не удаляем, не бракуем. Захочет владелец
отправить с прогретого домена - письма на месте.

Без аргумента - сухой прогон.

    python zapusk_svoego_skripta.py ops/vynut_korporativnye_iz_avto.py
    python zapusk_svoego_skripta.py ops/vynut_korporativnye_iz_avto.py --вынуть

ИТОГ ПЕРВОГО ПРИМЕНЕНИЯ (18.08, 03:20): вынимать оказалось НЕЧЕГО - все 26
писем уже отправлены. Автоотправка забрала их первыми: они были одобрены в
первой партии из 329, и их час в зоне получателя пришёл раньше московского.
Пока я мерил и спрашивал владельца - письма улетели.

Вывод на будущее: фильтр корпоративных серверов надо ставить НЕ на
генерацию, а на ВХОД В АВТООТПРАВКУ. В partiya_gen.py он защищает только то,
что генерирую я, а в approved письма попадают и другими путями.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

СВОЙ_СЕРВЕР = ("other", "unknown", "")
ВЫНУТЬ = "--вынуть" in sys.argv

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряд = store._conn.execute(
        "SELECT c.id, c.email, COALESCE(r.mx_provider,''), "
        "COALESCE(m.status,'') FROM confirm_reviews c "
        "JOIN recipients r ON r.id=c.recipient_id "
        "LEFT JOIN messages m ON m.id=c.message_id "
        "WHERE c.campaign_id=10 AND c.status='approved'").fetchall()

свои, уже_ушли = [], []
счёт = Counter()
for cid, email, mx, статус_письма in ряд:
    if str(mx).strip().lower() not in СВОЙ_СЕРВЕР:
        счёт[f"публичный: {mx}"] += 1
        continue
    if статус_письма == "sent":
        уже_ушли.append((cid, email))
        continue
    свои.append((cid, email, mx))

print(f"одобренных писем: {len(ряд)}")
print(f"  на свой сервер, ещё НЕ отправлены: {len(свои)}")
print(f"  на свой сервер, УЖЕ отправлены (поздно): {len(уже_ушли)}")
for k, n in счёт.most_common(6):
    print(f"  {k}: {n}")
for cid, email, mx in свои[:12]:
    print(f"    #{cid} {email:<40} mx={mx or '(пусто)'}")

if not ВЫНУТЬ:
    print("\nсухой прогон: ничего не тронуто. Вынуть - аргумент --вынуть")
    raise SystemExit(0)

вынуто = сбоев = 0
for cid, _email, _mx in свои:
    try:
        with store._lock:
            store._conn.execute(
                "UPDATE confirm_reviews SET status='pending', "
                "decided_at=NULL, decided_by=NULL, "
                "reason='снято из автоотправки: свой почтовый сервер', "
                "updated_at=datetime('now') WHERE id=? AND status='approved'",
                (cid,))
            store._conn.commit()
        вынуто += 1
    except Exception as ex:                                     # noqa: BLE001
        сбоев += 1
        if сбоев <= 5:
            print(f"  #{cid}: {type(ex).__name__} {str(ex)[:110]}")

with store._lock:
    осталось = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=10 "
        "AND status='approved'").fetchone()[0]
print(f"\nвынуто: {вынуто} | сбоев: {сбоев}")
print(f"в автоотправке осталось: {осталось}")
