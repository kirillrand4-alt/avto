# -*- coding: utf-8 -*-
"""Очередь по вердиктам рецензента: годные — в отправку, чужие — снять.

Владелец 20.08: «прогони рецензента, посмотри глазами что не прошло и
если наш профиль но мало данных — отправляй».

Прочитано глазами 61 письмо с вердиктом «не годно». Претензии делятся
надвое, и линия проходит не по строгости, а по СУТИ:

  * САЙТ ПОКАЗЫВАЕТ ДРУГОЕ ЗАНЯТИЕ — интернет-магазин вместо
    производства, торговая площадка вместо переработки, сайт вообще
    чужой компании, или отрасль вне канона (розлив воды — у Мейера
    напитки исключены). Такому письму первая же фраза врёт в лицо;
    снимаем с причиной.
  * ПРОФИЛЬ НАШ, А ПРЕТЕНЗИЯ К ДЕТАЛИ — число, марка стали, лишний
    товар в перечне, формулировка. «3000 тонн в месяц» против «40 000
    тонн в год» на заводе металлоконструкций; «полба» в перечне круп у
    крупяного завода. Это и есть «наш профиль, но мало данных» —
    отправляем.

«Нечем проверить» (сайт не открылся или пуст) — тоже отправляем: судить
не по чему, а профиль отобран ОКВЭДом и паспортом.

Кампании только 10 и 11. Старые 7-9 не трогаем.
Без --katit только показывает.
"""
import io
import json
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

ЖУРНАЛ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
КАТИТЬ = "--katit" in sys.argv

# ЧУЖОЕ ЗАНЯТИЕ — прочитано глазами, каждый id с причиной.
СНЯТЬ = {
    2802: "сайт — поставщик инструмента, письмо пишет им как производству",
    2805: "производят технические газы сами — не наш покупатель",
    2868: "письмо про дома из газобетона, сайт — многоэтажные ЖК и школы",
    2915: "сайт подтверждает поставку ЖБИ, не собственное производство",
    2948: "сайт принадлежит другой компании (Технолит), не получателю",
    2952: "сайт — интернет-магазин газового оборудования, не монтаж",
    2983: "сайт — интернет-магазин стройтехники, не производство",
    3010: "сайт — торговля дверями, не металлообработка у получателя",
    3207: "сайт — интернет-магазин капсул, не обжарка и фасовка",
    3238: "розлив воды: напитки вне канона Мейера",
    3293: "сайт — торговая площадка по икре, не производство",
    3324: "оптовая торговля мясом без своей переработки",
    3392: "письмо зовёт их строительной лабораторией, а они делают",
}

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
окно = window_from(store, cfg)
сейчас = datetime.now(timezone.utc)
АДР = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}$")

верд = {}
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        pass

with store._lock:
    строки = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.recipient_id, c.message_id, c.email, "
        "       r.inn, COALESCE(p.verdict,'') proba "
        "FROM confirm_reviews c "
        "LEFT JOIN recipients r ON r.id=c.recipient_id "
        "LEFT JOIN addr_probe p ON p.email=lower(c.email) "
        "WHERE c.status='pending' AND c.campaign_id IN (10,11)").fetchall()

счёт = Counter()
годные, на_снятие = [], []
for r in строки:
    rid = int(r["id"])
    v = верд.get(rid, "")
    if rid in СНЯТЬ:
        на_снятие.append((rid, СНЯТЬ[rid]))
        счёт["СНЯТЬ: сайт показывает другое занятие"] += 1
        continue
    if v not in ("годно", "нечем проверить", "не годно"):
        счёт[f"оставляем в очереди: {v or 'без вердикта'}"] += 1
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
    счёт[f"В ОТПРАВКУ ({v})"] += 1

print(f"карточек pending в кампаниях 10-11: {len(строки)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")

if not КАТИТЬ:
    print("\nсухой прогон. Катить — --katit")
    raise SystemExit(0)

снято = 0
for rid, причина in на_снятие:
    try:
        ок = store.confirm_decide(
            rid, status="skipped",
            reason=f"сайт показывает другое занятие: {причина}",
            decided_by="разбор по рецензии 20.08")
        снято += 1 if ок is not False else 0
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{rid} не снялось: {str(ex)[:90]}")

одобрено = слотов = 0
слоты = Counter()
for r in годные:
    try:
        ок = store.confirm_decide(int(r["id"]), status="approved",
                                  decided_by="разбор по рецензии 20.08")
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
print(f"одобрено в отправку: {одобрено} (слотов поставлено {слотов})")
print("слоты по дням:", dict(слоты))
