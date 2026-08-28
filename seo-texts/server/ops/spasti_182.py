# -*- coding: utf-8 -*-
"""Спасти 182 забракованных: определить направление и перегенерировать.

Владелец 28.08: «исправь и попробуй перегенерировать 182 что бы спасти».

Шаг 1 (этот файл): по паспорту сайта решаем, какого направления компания
покупатель — kc, meyer или никакого. Решение пишем в карточку получателя
(extra.target_division), откуда его первым приоритетом возьмёт генерация.
Шаг 2: обычная генерация по группе «Спасённые 182».

Тяжёлое — через провайдерский API. Без --katit ничего не пишет.
"""
import io
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402

КАТИТЬ = "--katit" in sys.argv
МОДЕЛЬ = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("модель=")),
              "claude-sonnet-4-6")
ПАЧКА = 8
СЛЕД = r"C:\sender\_ops\spasenie-182.jsonl"
ГРУППА = "Спасённые 182"

СИСТЕМА = """Ты классификатор промышленных компаний. По карточке компании
реши, какое из двух направлений поставщика может ей что-то продать.

КЦ — компрессорное оборудование: винтовые компрессоры, осушители, фильтрация,
генераторы азота и кислорода, пневмоинструмент. Годится почти любому, где есть
цех, стройка, монтаж, ремонт, техника, коммунальные сети, транспорт, добыча.

MEYER — контроль продукта: фотосепараторы (оптическая сортировка сыпучего
потока) и рентген-инспекция (поиск инородных включений в упакованном
продукте). Годится там, где есть ПОТОК ПРОДУКТА, который сортируют, фасуют
или упаковывают: пищёвка, переработка, зерно, крупа, орехи, комбикорм, фарма,
табак, вторсырьё.

НИКУДА — компания сама производит или продаёт такое оборудование (конкурент),
либо отрасль заведомо мимо: медицина и клиники, ИТ и разработка ПО, банки,
страхование, образование, консалтинг, реклама, чистые услуги без производства.

Компания может годиться обоим — тогда выбирай тот, где потребность очевиднее.
Сомневаешься между направлением и «никуда» — выбирай направление: пропустить
клиента дороже, чем написать лишнее письмо.

ОТВЕТ СТРОГО JSON:
{"firmy":[{"inn":"...","napravlenie":"kc|meyer|nikuda","pochemu":"одной фразой"}]}"""

# 182 забракованных судьёй
нельзя = {}
for с in io.open(r"C:\sender\_ops\sud-vtoryh.jsonl", encoding="utf-8"):
    try:
        d = json.loads(с)
    except Exception:                                            # noqa: BLE001
        continue
    if str(d.get("verdikt")) == "не отправлять":
        нельзя[int(d["id"])] = d
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(нельзя))
карточки = {}
for r in c.execute(
        "SELECT cr.id, cr.inn, cr.email, cr.recipient_id, r.company_name, r.okved "
        "  FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
        " WHERE cr.id IN (%s)" % зн, list(нельзя)):
    карточки[str(r["inn"])] = {
        "rev": int(r["id"]), "rid": r["recipient_id"], "email": r["email"],
        "имя": str(r["company_name"] or ""), "оквэд": str(r["okved"] or "")}
c.close()
print("забраковано судьёй: %d, компаний: %d" % (len(нельзя), len(карточки)))

e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=90)
e.row_factory = sqlite3.Row
инны = sorted(карточки)
зн2 = ",".join("?" * len(инны))
паспорт = {}
for r in e.execute("SELECT inn, facts_json FROM site_facts WHERE inn IN (%s)" % зн2,
                   инны):
    т = str(r["facts_json"] or "")
    if len(т) > len(паспорт.get(str(r["inn"]), "")):
        паспорт[str(r["inn"])] = т
акт = {}
for r in e.execute("SELECT inn, activity FROM companies WHERE inn IN (%s)" % зн2, инны):
    акт[str(r["inn"])] = str(r["activity"] or "")
e.close()
print("с паспортом сайта: %d" % len(паспорт))

сделано = {}
if os.path.exists(СЛЕД):
    for с in io.open(СЛЕД, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(с)
            сделано[str(d["inn"])] = d
        except Exception:                                        # noqa: BLE001
            pass
осталось = [и for и in инны if и not in сделано]
print("уже классифицировано: %d, осталось: %d" % (len(сделано), len(осталось)))


def блок(инн):
    к = карточки[инн]
    п = паспорт.get(инн, "")[:1200]
    return ("ИНН %s\nНАЗВАНИЕ: %s\nОКВЭД: %s\nПРОФИЛЬ: %s\nПАСПОРТ САЙТА: %s"
            % (инн, к["имя"], к["оквэд"][:80], акт.get(инн, "")[:200], п or "нет"))


def классифицировать(пачка):
    зов = "Компании:\n\n" + "\n\n".join(блок(и) for и in пачка)
    for попытка in range(3):
        try:
            m = GP._raw_stream([{"role": "user", "content": зов}], МОДЕЛЬ, 2000,
                               thinking=False, system=СИСТЕМА)
            т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
            мм = re.search(r"\{.*\}", т, re.S)
            if not мм:
                continue
            d = json.loads(мм.group(0))
            u = getattr(m, "usage", None)
            return (d.get("firmy") or [],
                    int(getattr(u, "input_tokens", 0) or 0),
                    int(getattr(u, "output_tokens", 0) or 0))
        except Exception as ex:                                  # noqa: BLE001
            print("   пачка сбойнула (%s)" % str(ex)[:60], flush=True)
            time.sleep(2 * (попытка + 1))
    return [], 0, 0


if осталось:
    пачки = [осталось[i:i + ПАЧКА] for i in range(0, len(осталось), ПАЧКА)]
    t0 = time.time()
    вх = вых = 0
    поток = io.open(СЛЕД, "a", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=4) as ex:
        for строки, i, o in ex.map(классифицировать, пачки):
            вх += i
            вых += o
            for x in строки:
                инн = str(x.get("inn") or "")
                if инн not in карточки:
                    continue
                сделано[инн] = x
                поток.write(json.dumps(x, ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
    поток.close()
    print("классификация: %.0f с, ~$%.3f"
          % (time.time() - t0, вх / 1e6 * 3.0 + вых / 1e6 * 15.0))

print("")
print("=== куда их ===")
for к, n in Counter(str(v.get("napravlenie")) for v in сделано.values()).most_common():
    print("   %-10s %4d" % (к, n))
if not КАТИТЬ:
    for инн, v in list(сделано.items())[:6]:
        print("   %-13s %-30s -> %-6s %s"
              % (инн, карточки[инн]["имя"][:30], v.get("napravlenie"),
                 str(v.get("pochemu"))[:52]))
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.ai_quota import build_ai_quota                         # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
итог = Counter()
for инн, v in сделано.items():
    напр = str(v.get("napravlenie") or "")
    к = карточки[инн]
    if напр not in ("kc", "meyer") or not к["rid"]:
        итог["никуда — не трогаем"] += 1
        continue
    if q._perestavit_napravlenie(int(к["rid"]), напр):
        итог["направление записано: " + напр] += 1
    else:
        итог["направление уже стояло: " + напр] += 1
    # метим группой, чтобы генерация взяла именно их
    try:
        with store.transaction() as conn:
            row = conn.execute("SELECT extra_json FROM recipients WHERE id=?",
                               (int(к["rid"]),)).fetchone()
            ex_ = json.loads((row[0] if row else None) or "{}") or {}
            гр = list(ex_.get("gruppy") or [])
            if ГРУППА not in гр:
                гр.append(ГРУППА)
                ex_["gruppy"] = гр
                conn.execute("UPDATE recipients SET extra_json=?, updated_at=? "
                             " WHERE id=?",
                             (json.dumps(ex_, ensure_ascii=False),
                              time.strftime("%Y-%m-%dT%H:%M:%S"), int(к["rid"])))
                итог["в группу"] += 1
    except Exception as ex2:                                     # noqa: BLE001
        итог["группа не легла: " + str(ex2)[:40]] += 1
print("")
print("=== итог ===")
for к, n in итог.most_common():
    print("   %-38s %4d" % (к, n))
