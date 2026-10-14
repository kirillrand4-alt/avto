# -*- coding: utf-8 -*-
"""Предклассификатор (мейер / кц / оба / никуда) по ВСЕМ компаниям групп
«Россия 9000» и «Белорусь 1000» (владелец 13.10: «давай покупатель/не
покупатель прогоним по всему списку — предклассификатор который»).

Промпт — ровно тот, что в генераторе (берём строку _ПРЕДКЛАСС_СИСТЕМА из
partiya_gen.py разбором исходника, чтобы правило было одно), паспорт — как в
генераторе (_site_facts). Решение каждой фирмы — в verdikty_v_bazy (обогащение
+ обзвон, источник «предкласс») и в _ops/predklass-vsey-bazy.jsonl (fsync);
повторный запуск продолжает с места.

    predklass_vsey_bazy.py           — сколько
    predklass_vsey_bazy.py --zapusk  — в фоне
    predklass_vsey_bazy.py --hod     — ход и свод
"""
import ast
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
ЖУРНАЛ = r"C:\sender\_ops\predklass-vsey-bazy.jsonl"
if "--zapusk" in sys.argv:
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"]
                         + (["--vne-grupp"] if "--vne-grupp" in sys.argv else []), cwd=r"C:\sender",
                         stdout=io.open(r"C:\sender\_ops\predklass-vsey-bazy.log", "w"), stderr=subprocess.STDOUT,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(8)
    print("запущено, pid %d, жив %s" % (п.pid, п.poll() is None))
    print("=== ПРЕДКЛАСС ВСЕЙ БАЗЫ: ЗАПУЩЕН ===")
    sys.exit(0)
if "--hod" in sys.argv:
    св, всего = Counter(), 0
    if os.path.exists(ЖУРНАЛ):
        for с in io.open(ЖУРНАЛ, encoding="utf-8"):
            з = json.loads(с)
            всего += 1
            св[з.get("napr")] += 1
    print("решено фирм: %d; %s" % (всего, dict(св.most_common())))
    try:
        print("лог: " + io.open(r"C:\sender\_ops\predklass-vsey-bazy.log", encoding="utf-8", errors="replace").read()[-300:])
    except Exception:  # noqa: BLE001
        pass
    print("=== ПРЕДКЛАСС ВСЕЙ БАЗЫ: ХОД ===")
    sys.exit(0)

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
sys.path.insert(0, r"C:\sender\server\ops")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
готово = set()
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8"):
        готово.add(json.loads(с)["inn"])
фирмы, видели = [], set()
for inn, имя, ex in c.execute("SELECT inn, company_name, extra_json FROM recipients WHERE extra_json LIKE '%gruppy%'"):
    inn = "".join(ч for ч in str(inn or "") if ч.isdigit())
    if not inn or inn in видели or inn in готово:
        continue
    if "Россия 9000" not in str(ex) and "Белорусь 1000" not in str(ex):
        continue
    видели.add(inn)
    фирмы.append((inn, имя or ""))
# ВНЕ ГРУПП (владелец 14.10: «да» на предкласс по базе с паспортами — под
# рассылку КЦ). Все ИНН с адресом (recipients + обогащение), у которых ещё нет
# вердикта направления; без паспорта отсеются ниже, как и в основном режиме.
if "--vne-grupp" in sys.argv:
    _e = sqlite3.connect(r"C:\sender\enrich.db", timeout=30)
    _есть_верд = {str(r[0]) for r in _e.execute("SELECT inn FROM companies WHERE verdikt_napr IS NOT NULL")}
    _имя = {str(r[0]): r[1] for r in _e.execute("SELECT inn, name FROM companies")}
    _инн = {str(r[0]) for r in c.execute("SELECT DISTINCT inn FROM recipients WHERE inn IS NOT NULL AND email LIKE '%@%'")}
    _инн |= {str(r[0]) for r in _e.execute("SELECT DISTINCT inn FROM emails WHERE email LIKE '%@%'")}
    for inn in sorted(_инн):
        inn = "".join(ч for ч in inn if ч.isdigit())
        if inn and inn not in видели and inn not in готово and inn not in _есть_верд:
            видели.add(inn)
            фирмы.append((inn, _имя.get(inn) or ""))
print("фирм к решению: %d (уже решено %d)" % (len(фирмы), len(готово)))
if "--rabota" not in sys.argv:
    print("=== ПРЕДКЛАСС ВСЕЙ БАЗЫ: СУХОЙ ПРОГОН ===")
    sys.exit(0)

import gen_provider  # noqa: E402
import verdikty_v_bazy as вб  # noqa: E402
исх = io.open(r"C:\sender\server\ops\partiya_gen.py", encoding="utf-8").read()
СИСТЕМА = next(ast.literal_eval(узел.value) for узел in ast.parse(исх).body
               if isinstance(узел, ast.Assign) and getattr(узел.targets[0], "id", "") == "_ПРЕДКЛАСС_СИСТЕМА")


def паспорт(инн):
    try:
        d = q._site_facts(инн) or {}
    except Exception:  # noqa: BLE001
        return ""
    куски = []
    for k in ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб", "мощности"):
        v = d.get(k)
        if v:
            куски.append(f"{k}: " + (v if isinstance(v, str) else "; ".join(map(str, v))[:260]))
    return "\n".join(куски)[:1200]


с_паспортом = [(инн, имя, паспорт(инн)) for инн, имя in фирмы]
с_паспортом = [x for x in с_паспортом if x[2]]
if "--vne-grupp" in sys.argv:
    # жирные паспорта первыми (владелец 14.10): больше полей и текста — раньше
    с_паспортом.sort(key=lambda x: (-x[2].count("\n"), -len(x[2])))
print("с паспортом: %d" % len(с_паспортом))
замок = threading.Lock()


def пачка(кусок):
    блоки = [f"ИНН {a} · {b}\n{p}" for a, b, p in кусок]
    for попытка in range(3):
        try:
            m = gen_provider._raw_stream([{"role": "user", "content": "Компании:\n\n" + "\n\n".join(блоки)}],
                                         "claude-sonnet-4-6", 8000, thinking=False, system=СИСТЕМА)
            т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
            мм = re.search(r"\{.*\}", т, re.S)
            д = json.loads(мм.group(0)) if мм else {}
            if not д.get("firmy"):
                raise ValueError("пустой разбор")
            break
        except Exception as е:  # noqa: BLE001
            д = {}
            print("пачка: попытка %d: %s" % (попытка + 1, str(е)[:80]))
            time.sleep(10)
    записи = []
    for v in д.get("firmy") or []:
        инн = "".join(ч for ч in str(v.get("inn") or "") if ч.isdigit())
        н = str(v.get("napravlenie") or "").strip().lower()
        if инн and н:
            записи.append({"inn": инн, "napr": н, "istochnik": "предкласс",
                           "rusprom": "не покупатель" if н == "никуда" else None,
                           "pochemu": "предклассификатор по паспорту (%s)" % ("вне групп 14.10" if "--vne-grupp" in sys.argv else "вся база 13.10")})
    with замок:
        вб.obnovit(записи)
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
            for з in записи:
                ж.write(json.dumps({"inn": з["inn"], "napr": з["napr"]}, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())


куски = [с_паспортом[i:i + 12] for i in range(0, len(с_паспортом), 12)]
with ThreadPoolExecutor(6 if "--vne-grupp" in sys.argv else 3) as пул:
    list(пул.map(пачка, куски))
print("готово: пачек %d" % len(куски))
