# -*- coding: utf-8 -*-
"""Кому ещё можем писать по КЦ (владелец 20.10). Компании (по ИНН) с адресом
направления КЦ (сегмент «кц» или target_division=kc), которым:
  * ещё не писали и письмо не стоит в работе (любой статус кроме skipped/failed);
  * адрес не в стоп-листе и не мёртв по пробе (у компании есть хоть один живой
    или непроверенный адрес в панели);
  * не было ответа (лид) по ИНН.
Разрез: по группам базы, по пробе лучшего адреса, крупные (выручка от 1 млрд)."""
import json
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect(r"C:\sender\sender.db")
e = sqlite3.connect(r"C:\sender\enrich.db")
таб = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
стоп = set()
for т in ("suppression", "suppressions", "stop_list"):
    if т in таб:
        кол = [r[1] for r in c.execute("PRAGMA table_info(%s)" % т)]
        к = next((x for x in ("email", "value", "address") if x in кол), None)
        if к:
            стоп |= {str(r[0]).lower() for r in c.execute("SELECT %s FROM %s" % (к, т))}
проба = {str(r[0]).lower(): str(r[1] or "") for r in c.execute("SELECT email, verdict FROM addr_probe")}
писали = {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "WHERE m.status NOT IN ('skipped','failed') AND r.inn IS NOT NULL")}
писали |= {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM send_log WHERE inn IS NOT NULL")}
лиды = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM leads WHERE inn IS NOT NULL")} if "leads" in таб else set()
выр = {str(r[0]): float(r[1] or 0) for r in e.execute("SELECT inn, revenue_rub FROM companies WHERE revenue_rub IS NOT NULL")}
РАНГ = {"есть": 0, "принимает всё": 1, "": 2, "неясно": 3, "отказ пробе": 4}
комп = defaultdict(lambda: {"гр": set(), "проба": 9})
сч = Counter()
for em, inn, seg, ex in c.execute("SELECT lower(email), inn, segment, extra_json FROM recipients WHERE inn IS NOT NULL AND inn!=''"):
    x = json.loads(ex or "{}")
    if not (str(seg or "") == "кц" or x.get("target_division") == "kc"):
        continue
    inn = str(inn)
    if inn in писали or inn in лиды:
        continue
    if em in стоп:
        сч["адрес в стоп-листе"] += 1
        continue
    в = проба.get(em, "")
    if в in ("нет ящика", "нет MX"):
        сч["адрес мёртв по пробе"] += 1
        continue
    к = комп[inn]
    к["гр"].update(x.get("gruppy") or ["без группы"])
    к["проба"] = min(к["проба"], РАНГ.get(в, 2))
имя = {v: k or "не проверен" for k, v in РАНГ.items()}
print("компаний КЦ, которым можем писать:", len(комп))
print("  отсеяно адресов:", dict(сч))
print("  по пробе лучшего адреса:", {имя[k]: v for k, v in sorted(Counter(к["проба"] for к in комп.values()).items())})
крупн = [i for i in комп if выр.get(i, 0) >= 1e9]
print("  крупных (выручка от 1 млрд):", len(крупн))
гр = Counter()
for к in комп.values():
    for g in к["гр"]:
        гр[g] += 1
print("  по группам базы (компания может быть в нескольких):", гр.most_common(12))
print("для сравнения: всего компаний КЦ, которым уже писали/в работе:", len(писали))


# ВЫРУЧКА (владелец 22.10: «какая выручка у этих 9670?») — только компании,
# которые идут в отправку: лучший адрес «есть»/«принимает всё»/не проверен.
def _полоса(в):
    if not в:
        return "0 нет данных"
    for п, имя_п in ((1e7, "1 до 10 млн"), (3e7, "2 10-30 млн"), (1e8, "3 30-100 млн"), (5e8, "4 100-500 млн"),
                     (1e9, "5 500 млн-1 млрд"), (1e10, "6 1-10 млрд")):
        if в < п:
            return имя_п
    return "7 от 10 млрд"


годн = [i for i, к in комп.items() if к["проба"] <= 2]
пол = Counter()
пол_есть = Counter()
for i in годн:
    п = _полоса(выр.get(i, 0))
    пол[п] += 1
    if комп[i]["проба"] == 0:
        пол_есть[п] += 1
print("\nв отправку (без «неясно»/«отказ»): %d | выручка (всего / из них «есть»):" % len(годн))
for п in sorted(пол):
    print("  %-18s %6d  %6d" % (п[2:], пол[п], пол_есть[п]))
