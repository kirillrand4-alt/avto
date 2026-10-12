# -*- coding: utf-8 -*-
"""Кто в партиях «идеален» для генерации: паспорт + адрес.

Владелец 12.10: «у кого всё идеально по паспортам и адресам — отправляй
на генерацию». Идеально значит:
  * паспорт с подтверждённого сайта: verified в {inn, ogrn, phone,
    provider, sam_sayt} (второй уровень — В/Г/Д — сюда не входит) и
    описание не короче 200 знаков;
  * адрес valid, MX живой, без приговора пробы (нет ящика / нет MX / битый);
  * ни ИНН, ни адрес не в стоп-листе; писем этому адресу ещё не было,
    кроме повторных по новому паспорту, которые владелец разрешил.
Выводит счёт и сохраняет список id в _ops (durable) для следующих шагов.
"""
import io
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ОК = {"inn", "ogrn", "phone", "provider", "sam_sayt"}
ГРУППЫ = ("Россия 9000", "Белорусь 1000")
ВЫХОД = r"C:\sender\_ops\idealnye-9000.json"

store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    приговор = {р[0] for р in c.execute(
        "SELECT lower(email) FROM addr_probe "
        "WHERE verdict IN ('нет MX','нет ящика','битый адрес')")}
    стоп_почта = {str(р[0]).lower() for р in c.execute(
        "SELECT value FROM suppression WHERE scope='email'")}
    стоп_инн = {str(р[0]) for р in c.execute(
        "SELECT value FROM suppression WHERE scope='inn'")}
    писали = {р[0] for р in c.execute(
        "SELECT DISTINCT m.recipient_id FROM messages m "
        "WHERE m.status IN ('sent','scheduled','claimed','pending_review')")}
    строки = []
    for р in c.execute(
            "SELECT id, inn, lower(email) e, valid_status v, segment s, "
            "extra_json x FROM recipients WHERE extra_json LIKE '%gruppy%'"):
        try:
            д = json.loads(р["x"] or "{}") or {}
        except Exception:  # noqa: BLE001
            continue
        гр = [г for г in (д.get("gruppy") or []) if г in ГРУППЫ]
        if гр:
            строки.append((dict(р), гр[0], bool(д.get("povtornoe"))))

cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
паспорт = {}
инны = list({р["inn"] for р, _, _ in строки if р["inn"]})
for н in range(0, len(инны), 400):
    к_ = инны[н:н + 400]
    for р in cx.execute("SELECT inn, verified, length(activity) d FROM companies "
                        "WHERE inn IN (%s)" % ",".join("?" * len(к_)), к_):
        паспорт[р["inn"]] = (str(р["verified"] or ""), int(р["d"] or 0))
cx.close()

свод = {г: Counter() for г in ГРУППЫ}
идеальные = {г: [] for г in ГРУППЫ}
по_отрасли = Counter()
for р, г, повтор in строки:
    с = свод[г]
    с["всего"] += 1
    вер, длина = паспорт.get(р["inn"], ("", 0))
    if р["inn"] in стоп_инн or р["e"] in стоп_почта:
        с["мимо: стоп-лист"] += 1
        continue
    if р["v"] != "valid":
        с["мимо: адрес не valid (%s)" % р["v"]] += 1
        continue
    if р["e"] in приговор:
        с["мимо: приговор пробы"] += 1
        continue
    if вер not in ОК:
        с["мимо: паспорт 2-го уровня/без доверия"] += 1
        continue
    if длина < 200:
        с["мимо: паспорт короче 200 знаков"] += 1
        continue
    if р["id"] in писали and not повтор:
        с["мимо: письмо этому адресу уже есть"] += 1
        continue
    с["ИДЕАЛЬНО"] += 1
    if повтор:
        с["  из них повторных"] += 1
    идеальные[г].append(р["id"])
    по_отрасли[str(р["s"] or "")] += 1

json.dump({г: идеальные[г] for г in ГРУППЫ},
          io.open(ВЫХОД, "w", encoding="utf-8"), ensure_ascii=False)
for г in ГРУППЫ:
    print("")
    print("--- %s ---" % г)
    for к, n in sorted(свод[г].items(), key=lambda x: -x[1]):
        print("   %-40s %6d" % (к, n))
print("")
print("--- идеальные по отраслям ---")
for о, n in по_отрасли.most_common():
    print("   %-36s %5d" % (о[:36], n))
print("")
print("=== ИДЕАЛЬНЫЕ ДЛЯ ГЕНЕРАЦИИ ===")
for г in ГРУППЫ:
    print("   %-16s %5d из %5d" % (г, свод[г]["ИДЕАЛЬНО"], свод[г]["всего"]))
print("   список id: %s" % ВЫХОД)
