# -*- coding: utf-8 -*-
"""Пробы работником VPS по группе «КЦ тест» + лесенка (владелец 15.10: «отправь
пробы по ним и лесенку»). Для каждой компании группы: адрес группы и запасные
адреса компании из обогащения (лесенка, до 4 на компанию, без кадров/бухгалтерии),
которые работник ещё не проверял. Кладём В ГОЛОВУ задания на дропе, чужие адреса
задания сохраняем, будим работника. Вердикты приедут в addr_probe штатным
ProbeSync; генерация сама возьмёт следующий живой по лесенке.

    proba_kc_test.py              посчитать
    proba_kc_test.py --otpravit   отдать
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import build_addr_probe                # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.probe_sync import build_probe_sync, ЗАДАНИЕ       # noqa: E402
from sender.store import Store                                # noqa: E402

ОТПРАВИТЬ = "--otpravit" in sys.argv
НЕ_ДЛЯ = ("кадр", "бухгалт", "пресс", "hr", "резюме", "вакан")
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
проба = build_addr_probe(store, cfg)
цикл = build_probe_sync(store, getattr(проба, "probe_", проба), cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
проверено = {str(r[0]).lower(): r[1] for r in c.execute("SELECT email, verdict FROM addr_probe WHERE source='проба'")}
главный = {}
for inn, em in c.execute("SELECT inn, lower(email) FROM recipients WHERE extra_json LIKE '%КЦ тест%'"):
    главный[str(inn)] = em
лесенка = defaultdict(list)
for inn, em, роль, mx in e.execute("SELECT inn, lower(email), COALESCE(role,''), mx_ok FROM emails WHERE email LIKE '%@%'"):
    inn = str(inn)
    if inn in главный and em != главный[inn] and mx != 0 and not any(с in роль.lower() for с in НЕ_ДЛЯ):
        лесенка[inn].append(em)
счёт, голова, хвост = Counter(), [], []
for inn, em in главный.items():
    if em in проверено:
        счёт["адрес группы: уже проверен (%s)" % проверено[em]] += 1
    else:
        голова.append(em)
        счёт["адрес группы: в пробу"] += 1
    for а in лесенка[inn][:4]:
        if а in проверено:
            счёт["лесенка: уже проверен"] += 1
        else:
            хвост.append(а)
            счёт["лесенка: в пробу"] += 1
порядок, видели = [], set()
for а in голова + хвост:
    if а not in видели:
        видели.add(а)
        порядок.append(а)
print("компаний в группе: %d" % len(главный))
for к, n in счёт.most_common():
    print("   %5d  %s" % (n, к))
print("адресов к отправке работнику: %d" % len(порядок))
было = []
try:
    было = json.loads(цикл._дроп("GET", ЗАДАНИЕ).decode("utf-8", "replace"))
    if isinstance(было, dict):
        было = было.get("emails") or []
except Exception as ex:                                       # noqa: BLE001
    print("задания на дропе нет: %s" % str(ex)[:80])
print("сейчас в задании: %d" % len(было or []))
if not ОТПРАВИТЬ:
    print("=== ПРОБА КЦ ТЕСТ: сухой прогон ===")
    raise SystemExit(0)
наши = set(порядок)
список = порядок + [x for x in dict.fromkeys(str(x).strip().lower() for x in (было or [])) if x and x not in наши]
цикл._дроп("PUT", ЗАДАНИЕ, json.dumps(список, ensure_ascii=False).encode("utf-8"))
try:
    цикл._толкнуть(len(список))
    print("работник разбужен")
except Exception as ex:                                       # noqa: BLE001
    print("толчок не вышел: %s" % str(ex)[:100])
print("в задании теперь: %d (наших %d в голове)" % (len(список), len(порядок)))
print("=== ПРОБА КЦ ТЕСТ: ОТДАНО ===")
