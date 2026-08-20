# -*- coding: utf-8 -*-
"""Разбор старых кампаний 7-9 после переписи с паспортом.

46 карточек переписаны заново с паспортом сайта, рецензент прочитал их
впервые (раньше он в эти кампании не заходил). Дальше руками, по тому же
правилу, что и основная очередь.

СНЯТЬ «чужое занятие» — сайт показывает не то дело, о котором письмо:
торговая площадка вместо переработки, дистрибьютор вместо производителя,
B2B-супермаркет вместо завода, продажа станков вместо их выпуска.

СНЯТЬ «ждём» — переписать с паспортом так и не вышло: гейт бракует
письмо на каждой попытке, а отправлять старый текст, написанный БЕЗ
профиля, — ровно то, чего владелец просил не делать.

Остальным ставим слот: профиль наш, претензии рецензента — к детали
(перечень культур, вид сухарей, «штамповка» вместо «литья»).
"""
import re
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.auto_send import (next_slot, recipient_tz_name,      # noqa: E402
                              window_from)
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

КАТИТЬ = "--katit" in sys.argv

ЧУЖОЕ = {
    972: "yagod-market.com — биржа объявлений, а не переработка ягод",
    1018: "сайт определяет компанию как дистрибьютора, не производителя",
    1056: "торгово-дилерская снабженческая компания, производства нет",
    1058: "продают оборудование и врезку, а не выпускают станки",
}
ЖДЁМ = {
    987: "перепись с паспортом не вышла: гейт бракует на каждой попытке",
    1010: "перепись с паспортом не вышла: шлюз отказывает по своей политике",
    1013: "перепись с паспортом не вышла: гейт бракует на каждой попытке",
    1069: "перепись с паспортом не вышла: цех не подтверждается сайтом",
}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
АДР = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")

with store._lock:
    строки = store._conn.execute(
        "SELECT c.id, c.recipient_id, c.message_id, c.email, r.inn, "
        "       COALESCE(p.verdict,'') proba "
        "FROM confirm_reviews c "
        "LEFT JOIN recipients r ON r.id=c.recipient_id "
        "LEFT JOIN addr_probe p ON p.email=lower(c.email) "
        "WHERE c.status='pending' AND c.campaign_id NOT IN (10,11)").fetchall()

счёт = Counter()
годные, снять = [], []
for r in строки:
    rid = int(r["id"])
    if rid in ЧУЖОЕ:
        снять.append((rid, "сайт показывает другое занятие: " + ЧУЖОЕ[rid]))
        счёт["СНЯТЬ: чужое занятие"] += 1
        continue
    if rid in ЖДЁМ:
        снять.append((rid, "ждём: " + ЖДЁМ[rid]))
        счёт["СНЯТЬ: ждём переписи"] += 1
        continue
    e = str(r["email"] or "").strip().lower()
    плохо = []
    if not АДР.match(e):
        плохо.append("формат адреса")
    if str(r["proba"]) in ("нет ящика", "нет MX"):
        плохо.append(f"приговор пробы: {r['proba']}")
    try:
        причина = cs._guard(inn=str(r["inn"] or ""), email=e)
        if причина:
            плохо.append(f"заслон: {причина.split(':')[0]}")
    except Exception as ex:                                      # noqa: BLE001
        плохо.append(f"заслон не отработал: {str(ex)[:40]}")
    try:
        from sender.lovushki import заглушка
        if заглушка(e):
            плохо.append("адрес-заглушка")
    except Exception:                                            # noqa: BLE001
        pass
    if плохо:
        for p in плохо:
            счёт[f"не проходит адрес: {p}"] += 1
        continue
    годные.append(r)
    счёт["В ОТПРАВКУ"] += 1

print(f"карточек старых кампаний: {len(строки)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

снято = 0
for rid, причина in снять:
    try:
        ок = store.confirm_decide(rid, status="skipped", reason=причина,
                                  decided_by="разбор старых кампаний 20.08")
        снято += 1 if ок is not False else 0
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{rid} не снялось: {str(ex)[:90]}")

одобрено = слотов = 0
слоты = Counter()
for r in годные:
    try:
        ок = store.confirm_decide(int(r["id"]), status="approved",
                                  decided_by="разбор старых кампаний 20.08")
        if ок is False:
            continue
        одобрено += 1
        rec = store.get_recipient(r["recipient_id"])
        if r["message_id"] and rec is not None:
            с = next_slot(окно, recipient_tz_name(окно, rec), сейчас)
            store.reschedule_message(int(r["message_id"]), с)
            слотов += 1
            слоты[str(с)[:10]] += 1
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{r['id']} не одобрилось: {str(ex)[:90]}")

print(f"\nснято с причиной: {снято}")
print(f"одобрено в отправку: {одобрено} (слотов {слотов})")
print("слоты по дням:", dict(слоты))
