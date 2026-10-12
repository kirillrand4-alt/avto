# -*- coding: utf-8 -*-
"""Подготовить 500 писем: кампания + отбор вперемешку по отраслям.

Владелец 12.10: «500 писем из разных групп (молоко/дерево/руды и тд) жду
от тебя, а паспорт — проверь, чтобы наиболее полно используем информацию
с сайта». Здесь только отбор и проверка полноты паспорта, без генерации.

Отбор: из «идеальных» (idealnye-9000.json, группа «Россия 9000»), по
отраслям — у каждой отрасли не меньше 15, остальное пропорционально;
внутри отрасли — сначала самые полные паспорта.
Список кладём в _ops/partiya-500.json (durable), генерация берёт его.
"""
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

ВСЕГО = 500
МИНИМУМ = 15
КЛЮЧИ = ("продукция", "сырьё", "мощности", "контроль_качества",
         "оборудование_линии", "упаковка_фасовка", "экспорт", "масштаб")

ид = json.load(io.open(r"C:\sender\_ops\idealnye-9000.json", encoding="utf-8"))
кандидаты = ид.get("Россия 9000") or []
store = Store(r"C:\sender\sender.db")
with store._lock:
    c = store._conn
    м = ",".join("?" * len(кандидаты))
    строки = [dict(р) for р in c.execute(
        "SELECT id, inn, lower(email) e, segment s FROM recipients "
        "WHERE id IN (%s)" % м, кандидаты)]
    камп = [dict(р) for р in c.execute(
        "SELECT id, name, status, legal_entity, legal_inn, provider_pool, "
        "config_json FROM campaigns ORDER BY id")]
print("кампании в базе:")
for к in камп:
    print("   #%-3s %-34s %-9s пул=%s" % (к["id"], str(к["name"])[:34],
                                       к["status"], к["provider_pool"]))

cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
инны = list({р["inn"] for р in строки if р["inn"]})
полнота, текст_сайта, длина_акт = {}, set(), {}
for н in range(0, len(инны), 400):
    к_ = инны[н:н + 400]
    м = ",".join("?" * len(к_))
    for р in cx.execute("SELECT inn, facts_json FROM site_facts "
                        "WHERE inn IN (%s)" % м, к_):
        try:
            д = json.loads(р["facts_json"] or "{}") or {}
        except Exception:  # noqa: BLE001
            д = {}
        полнота[р["inn"]] = sum(1 for к in КЛЮЧИ if д.get(к))
    try:
        for р in cx.execute("SELECT inn FROM site_text WHERE inn IN (%s) "
                            "AND length(text) > 300" % м, к_):
            текст_сайта.add(р["inn"])
    except sqlite3.OperationalError:
        pass
    for р in cx.execute("SELECT inn, length(activity) d FROM companies "
                        "WHERE inn IN (%s)" % м, к_):
        длина_акт[р["inn"]] = int(р["d"] or 0)
cx.close()

по_отр = defaultdict(list)
for р in строки:
    по_отр[р["s"] or "(нет)"].append(р)
for о in по_отр:
    по_отр[о].sort(key=lambda р: (-полнота.get(р["inn"], 0),
                                  -длина_акт.get(р["inn"], 0), р["id"]))
отрасли = [о for о in по_отр if о != "Прочее"]
доля = {о: max(МИНИМУМ, round(ВСЕГО * len(по_отр[о]) / max(1, len(строки))))
        for о in отрасли}
while sum(доля.values()) > ВСЕГО:
    о = max(доля, key=lambda x: доля[x])
    доля[о] -= 1
while sum(доля.values()) < ВСЕГО:
    о = max(отрасли, key=lambda x: len(по_отр[x]) - доля[x])
    доля[о] += 1
выбор = []
for о in отрасли:
    выбор.extend(по_отр[о][:доля[о]])

json.dump([р["id"] for р in выбор],
          io.open(r"C:\sender\_ops\partiya-500.json", "w", encoding="utf-8"))

print("")
print("--- 500 по отраслям ---")
for о in sorted(отрасли, key=lambda x: -доля[x]):
    сп = по_отр[о][:доля[о]]
    п = sum(полнота.get(р["inn"], 0) for р in сп) / max(1, len(сп))
    т = sum(1 for р in сп if р["inn"] in текст_сайта)
    print("   %-34s %4d   разделов паспорта ~%.1f из 8, текст сайта %d"
          % (о[:34], len(сп), п, т))
пол = Counter(полнота.get(р["inn"], 0) for р in выбор)
print("")
print("--- полнота паспорта у выбранных (разделов из 8) ---")
for k in sorted(пол, reverse=True):
    print("   %d разделов: %4d" % (k, пол[k]))
print("")
print("=== ПОДГОТОВКА 500 ===")
print("   выбрано: %d из %d идеальных" % (len(выбор), len(строки)))
print("   с живым текстом сайта: %d" % sum(1 for р in выбор if р["inn"] in текст_сайта))
print("   паспорт 4+ разделов:  %d" % sum(1 for р in выбор if полнота.get(р["inn"], 0) >= 4))
