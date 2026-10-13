# -*- coding: utf-8 -*-
"""Проверка «покупатель / не покупатель» (гейт адресата) по всем компаниям групп
«Россия 9000» и «Белорусь 1000», у которых вердикта ещё нет (владелец 13.10:
«давай покупатель/не покупатель прогоним по всему списку»).

Тот же TargetGate и та же линза, что в прогоне (sonnet через провайдера),
пачки по 8. Вердикт пишет сам гейт в sender.db/target_verdicts (кэш —
повторно не платим), в конце — verdikty_v_bazy (обогащение + обзвон).
Компании из списка текущего прогона пропускаем: их судит сам прогон.

    geyt_vsey_bazy.py              — сколько судить
    geyt_vsey_bazy.py --zapusk     — в фоне
    geyt_vsey_bazy.py --hod        — ход
"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
ХОД = r"C:\sender\_ops\geyt-vsey-bazy.json"
if "--hod" in sys.argv:
    try:
        print(io.open(ХОД, encoding="utf-8").read())
    except Exception as е:  # noqa: BLE001
        print("хода нет: %s" % е)
    print("=== ГЕЙТ ВСЕЙ БАЗЫ: ХОД ===")
    sys.exit(0)
if "--zapusk" in sys.argv:
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"], cwd=r"C:\sender",
                         stdout=io.open(r"C:\sender\_ops\geyt-vsey-bazy.log", "w"), stderr=subprocess.STDOUT,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(8)
    print("запущено, pid %d, жив %s" % (п.pid, п.poll() is None))
    print("=== ГЕЙТ ВСЕЙ БАЗЫ: ЗАПУЩЕН ===")
    sys.exit(0)

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
есть = {str(р[0]) for р in c.execute("SELECT inn FROM target_verdicts")}
в_прогоне = set(json.load(io.open(r"C:\sender\_ops\partiya-deshevye.json", encoding="utf-8")))
судить, видели = [], set()
for rid, inn, ex in c.execute("SELECT id, inn, extra_json FROM recipients WHERE extra_json LIKE '%gruppy%'"):
    if not inn or str(inn) in есть or str(inn) in видели or rid in в_прогоне:
        continue
    if "Россия 9000" not in str(ex) and "Белорусь 1000" not in str(ex):
        continue
    видели.add(str(inn))
    судить.append(rid)
print("в группах без вердикта: %d компаний (из прогона исключено %d)" % (len(судить), len(в_прогоне)))
if "--rabota" not in sys.argv:
    print("=== ГЕЙТ ВСЕЙ БАЗЫ: СУХОЙ ПРОГОН ===")
    sys.exit(0)

from sender.review_lenses import default_caller  # noqa: E402
from sender.target_gate import TargetGate  # noqa: E402
q = build_ai_quota(store, cfg)
гейт = TargetGate(cfg.get("service.db_path", r"C:\sender\sender.db"),
                  lambda p: default_caller(p, model="claude-sonnet-4-6")[0])
компании = []
for rid in судить:
    r = store.get_recipient(rid)
    try:
        карточка = q._card_for(r.inn) or {}
    except Exception:  # noqa: BLE001
        карточка = {}
    ec = (карточка.get("enrich") or {}).get("company") or {}
    try:
        паспорт = q._pasport_dlya_geyta(str(r.inn))
    except Exception:  # noqa: BLE001
        паспорт = ""
    компании.append({"inn": str(r.inn), "name": r.company_name or ec.get("name") or "",
                     "okved": r.okved or ec.get("okved") or "", "activity": ec.get("activity") or "",
                     "pasport": паспорт})
куски = [компании[i:i + 8] for i in range(0, len(компании), 8)]
ход = {"всего": len(компании), "пачек": len(куски), "готово_пачек": 0, "не_покупатели": 0, "сбоев": 0,
       "старт": time.strftime("%H:%M:%S")}


def отметить():
    with io.open(ХОД, "w", encoding="utf-8") as ф:
        json.dump(ход, ф, ensure_ascii=False)


def судить_пачку(к):
    try:
        н = гейт.not_buyers(к, source="вся-база")
        ход["не_покупатели"] += len(н)
    except Exception as е:  # noqa: BLE001
        ход["сбоев"] += 1
        print("пачка не осуждена: %s" % str(е)[:100])
    ход["готово_пачек"] += 1
    if ход["готово_пачек"] % 10 == 0:
        отметить()


отметить()
with ThreadPoolExecutor(6) as пул:
    list(пул.map(судить_пачку, куски))
ход["финиш"] = time.strftime("%H:%M:%S")
отметить()
import verdikty_v_bazy  # noqa: E402,F401
subprocess.run([sys.executable, r"C:\sender\server\ops\verdikty_v_bazy.py", "--primenit"], timeout=1800)
print("готово", ход)
