# -*- coding: utf-8 -*-
"""Сколько ещё компаний «того же качества», что вчерашние письма до $0.30.

1) По журналу 9000 за 12–13.10: цена годного письма по (отрасль × полнота
   паспорта). Ячейки, где годное ≤ ПОРОГ и попыток ≥ 8, — «то же качество».
2) Кандидаты: группы «Россия 9000»/«Белорусь 1000», ещё не генерировали
   (журнал), заслон confirm пропускает, адрес не мёртв по пробе; считаем,
   сколько попадает в эти ячейки (и сколько из них с подтверждённым адресом).

    kandidaty_do_30c.py [porog=0.30]
"""
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict
sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.confirm import ConfirmSend  # noqa: E402
from sender.suppression import Suppression  # noqa: E402

арг = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
ПОРОГ = float(арг.get("porog", "0.30"))
ОБРАЗЦЫ = int(арг.get("obrazcy", "0"))   # >0: по N из каждой отрасли ВНЕ дешёвых ячеек
ПАУЗА = {"Лес и деревообработка", "Металлургия"}
КЛЮЧИ = ("продукция", "сырьё", "мощности", "контроль_качества",
         "оборудование_линии", "упаковка_фасовка", "экспорт", "масштаб")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)

получатели = {}
for р in c.execute("SELECT id, inn, lower(email) e, segment, extra_json FROM recipients WHERE extra_json LIKE '%gruppy%'"):
    try:
        гр = (json.loads(р["extra_json"] or "{}") or {}).get("gruppy") or []
    except Exception:  # noqa: BLE001
        continue
    if any(г in гр for г in ("Россия 9000", "Белорусь 1000")):
        получатели[р["id"]] = (р["inn"], р["e"], р["segment"] or "?")
инны = list({v[0] for v in получатели.values() if v[0]})
полнота = {}
for н in range(0, len(инны), 400):
    к = инны[н:н + 400]
    for inn, fj in cx.execute("SELECT inn, facts_json FROM site_facts WHERE inn IN (%s)" % ",".join("?" * len(к)), к):
        try:
            д = json.loads(fj or "{}") or {}
        except Exception:  # noqa: BLE001
            д = {}
        полнота[inn] = sum(1 for кл in КЛЮЧИ if д.get(кл))


def корзина(n):
    return "6-8" if n >= 6 else "4-5" if n >= 4 else "2-3" if n >= 2 else "0-1"


цена, годн, поп = defaultdict(float), Counter(), Counter()
были = set()
видели = set()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    rid = z.get("recipient_id")
    были.add(rid)
    if z.get("этап") != "итог" or str(z.get("день") or "") < "2026-10-12":
        continue
    ключ_зап = (rid, z.get("цена_$"), z.get("сек"))
    if ключ_зап in видели:
        continue
    видели.add(ключ_зап)
    v = получатели.get(rid)
    if not v:
        continue
    я = (v[2], корзина(полнота.get(v[0], 0)))
    поп[я] += 1
    цена[я] += float(z.get("цена_$") or 0)
    годн[я] += 1 if z.get("ок") else 0
хорошие = {я for я in поп if поп[я] >= 8 and годн[я] and цена[я] / годн[я] <= ПОРОГ}
if арг.get("vse"):
    хорошие = {(сег, корзина(полнота.get(v[0], 0))) for v in получатели.values() for сег in [v[2]]}
print("ячейки (отрасль × полнота) с годным ≤ $%.2f при ≥8 попытках:" % ПОРОГ)
for я in ([] if арг.get("vse") else sorted(хорошие, key=lambda x: цена[x] / годн[x])):
    print("   %-32s %-4s попыток %4d годных %4d  $%.3f" % (я[0][:32], я[1], поп[я], годн[я], цена[я] / годн[я]))

вер = {р[0].lower(): р[1] for р in c.execute("SELECT email, verdict FROM addr_probe")}
св = Counter()
по_ячейке = Counter()
образцы = {}
for rid, (inn, е, сег) in sorted(получатели.items(), key=lambda x: -полнота.get(x[1][0], 0)):
    я = (сег, корзина(полнота.get(inn, 0)))
    if ОБРАЗЦЫ:
        if я in хорошие or сег in ПАУЗА or len(образцы.get(сег, [])) >= ОБРАЗЦЫ:
            continue
    elif я not in хорошие:
        continue
    if rid in были:
        св["уже генерировали"] += 1
        continue
    if вер.get(е) in ("нет ящика", "нет MX"):
        св["адрес мёртв"] += 1
        continue
    п = cs._guard(inn=inn, email=е)
    if п:
        св["заслон: " + п.split(":")[0]] += 1
        continue
    св["КАНДИДАТ"] += 1
    if ОБРАЗЦЫ:
        if вер.get(е) not in ("есть", "принимает всё"):
            continue
        образцы.setdefault(сег, []).append(rid)
    св["   из них адрес подтверждён пробой" if вер.get(е) in ("есть", "принимает всё") else "   из них адрес ещё не проверен/неясно"] += 1
    по_ячейке[я] += 1
for к, n in св.most_common():
    print("   %-40s %d" % (к, n))
_по_отр = Counter()
for я, n in по_ячейке.items():
    _по_отр[я[0]] += n
print("кандидаты по отраслям: %s" % ", ".join("%s: %d" % (о[:22], n) for о, n in _по_отр.most_common()))
print("кандидаты по ячейкам: %s" % ", ".join("%s/%s: %d" % (я[0][:18], я[1], n) for я, n in по_ячейке.most_common(14)))
if ОБРАЗЦЫ:
    import io as _io
    сп = [rid for v in образцы.values() for rid in v]
    json.dump(сп, _io.open(r"C:\sender\_ops\partiya-obrazcy.json", "w", encoding="utf-8"))
    print("образцы: %d в _ops/partiya-obrazcy.json: %s" % (len(сп), {к: len(v) for к, v in образцы.items()}))
print("=== КАНДИДАТЫ ДО $%.2f ===" % ПОРОГ)
