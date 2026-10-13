# -*- coding: utf-8 -*-
"""500 писем по адресам, подтверждённым пробой, — самые богатые паспорта
в самых дешёвых отраслях (владелец 12.10: «есть ящик и принимает всё давай
сгенерим где побогаче паспорта штук 500, выбери которые должны подешевле
пройти»).

Отбор:
  * группа «Россия 9000», основной адрес с вердиктом пробы «есть» или
    «принимает всё» (sender.db/addr_probe);
  * компания ещё не попадала в генерацию (журнал 9000) и ей не писали
    (messages по получателю);
  * отрасль из дешёвых: цена годного письма по журналу 9000 не выше порога,
    лес и металл на паузе;
  * внутри — по полноте паспорта (разделов site_facts), потом по длине
    профиля.
Список в _ops/partiya-500-proba.json, генерация берёт его аргументом spisok.

    podgotovit_500_proba.py [vsego=500] [porog_otrasli=0.40]
"""
import io
import json
import sqlite3
import sys
from collections import Counter, defaultdict

арг = dict(а.split("=", 1) for а in sys.argv[1:] if "=" in а)
ВСЕГО = int(арг.get("vsego", "500"))
ПОРОГ = float(арг.get("porog_otrasli", "0.40"))
ПАУЗА = {"Лес и деревообработка", "Металлургия"}
КЛЮЧИ = ("продукция", "сырьё", "мощности", "контроль_качества",
         "оборудование_линии", "упаковка_фасовка", "экспорт", "масштаб")
ВЫХОД = арг.get("vyhod", r"C:\sender\_ops\partiya-500-proba.json")
ДОБАВИТЬ = арг.get("dobavit", "")  # json-список rid, идут первыми вне отбора

c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
вердикт = {р["email"].lower(): р["verdict"] for р in c.execute(
    "SELECT email, verdict FROM addr_probe")}
получатели = []
for р in c.execute("SELECT id, inn, lower(email) e, segment s, extra_json FROM recipients "
                   "WHERE extra_json LIKE '%Россия 9000%'"):
    try:
        д = json.loads(р["extra_json"] or "{}")
    except Exception:  # noqa: BLE001
        continue
    if "Россия 9000" not in (д.get("gruppy") or []):
        continue
    получатели.append({"id": р["id"], "inn": р["inn"], "e": р["e"], "s": р["s"] or "(нет)",
                       "v": вердикт.get(р["e"] or "")})
писали = {r[0] for r in c.execute("SELECT DISTINCT recipient_id FROM messages")}
# компании (по ИНН), которым за 90 дней уже ушло письмо на любой адрес, —
# не «лучшие новые»: их квота отдельное решение владельца (13.10, 42 фирмы)
писали_инн = {str(r[0]) for r in c.execute(
    "SELECT DISTINCT r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    "WHERE m.status='sent' AND m.sent_at >= datetime('now','-90 days')") if r[0]}

# цена годного по отраслям — из журнала 9000
отр_по_rid = {р["id"]: р["s"] for р in получатели}
были, цена, годн, поп = set(), defaultdict(float), Counter(), Counter()
for с in io.open(r"C:\sender\_ops\gen-rossiya-9000.jsonl", encoding="utf-8", errors="replace"):
    try:
        z = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    rid = z.get("recipient_id")
    были.add(rid)
    о = отр_по_rid.get(rid)
    if not о:
        continue
    поп[о] += 1
    цена[о] += float(z.get("цена_$") or 0)
    if z.get("ок"):
        годн[о] += 1
print("--- отрасли по журналу 9000 (попыток / годных / $ за годное) ---")
дешёвые = set()
цена_отр = {}
for о in sorted(поп, key=lambda x: цена[x] / max(1, годн[x])):
    за = цена[о] / годн[о] if годн[о] else 99
    ок = за <= ПОРОГ and поп[о] >= 6 and о not in ПАУЗА
    цена_отр[о] = за
    if ок:
        дешёвые.add(о)
    print("   %-32s %4d %4d  $%5.2f %s" % (о[:32], поп[о], годн[о], за, "<- берём" if ок else ""))

пригодные = [р for р in получатели if р["v"] in ("есть", "принимает всё")
             and р["id"] not in были and р["id"] not in писали and р["s"] in дешёвые
             and str(р["inn"] or "") not in писали_инн]
print("подтверждено пробой: %d; из них ещё не генерировали и не писали, в дешёвых отраслях: %d"
      % (sum(1 for р in получатели if р["v"] in ("есть", "принимает всё")), len(пригодные)))

cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
инны = list({р["inn"] for р in пригодные if р["inn"]})
полнота, длина = {}, {}
for н in range(0, len(инны), 400):
    к_ = инны[н:н + 400]
    м = ",".join("?" * len(к_))
    for р in cx.execute("SELECT inn, facts_json FROM site_facts WHERE inn IN (%s)" % м, к_):
        try:
            д = json.loads(р["facts_json"] or "{}") or {}
        except Exception:  # noqa: BLE001
            д = {}
        полнота[р["inn"]] = sum(1 for к in КЛЮЧИ if д.get(к))
    for р in cx.execute("SELECT inn, length(activity) d FROM companies WHERE inn IN (%s)" % м, к_):
        длина[р["inn"]] = int(р["d"] or 0)
# Вперёд — богаче паспорт («лучшие»), при равном — дешёвая отрасль (до
# $0.25 за годное): запуск с бюджетом обрывается на сумме.
пригодные.sort(key=lambda р: (-полнота.get(р["inn"], 0),
                              0 if цена_отр.get(р["s"], 99) <= 0.25 else 1,
                              -длина.get(р["inn"], 0), р["id"]))
доп = json.load(io.open(ДОБАВИТЬ, encoding="utf-8")) if ДОБАВИТЬ else []
выбор = [р for р in получатели if р["id"] in set(доп)] + [
    р for р in пригодные if р["id"] not in set(доп)][:ВСЕГО]
print("добавлено вне отбора: %d" % len(доп))
with io.open(ВЫХОД, "w", encoding="utf-8") as ф:
    json.dump([р["id"] for р in выбор], ф)
print("--- выбрано по отраслям ---")
for о, n in Counter(р["s"] for р in выбор).most_common():
    print("   %-32s %4d" % (о[:32], n))
print("--- полнота паспорта (разделов из 8) ---")
пол = Counter(полнота.get(р["inn"], 0) for р in выбор)
print("   " + ", ".join("%d: %d" % (k, пол[k]) for k in sorted(пол, reverse=True)))
print("вердикт пробы: %s" % dict(Counter(р["v"] for р in выбор)))
print("=== ОТБОР 500 ПО ПРОБЕ: %d в %s ===" % (len(выбор), ВЫХОД))
