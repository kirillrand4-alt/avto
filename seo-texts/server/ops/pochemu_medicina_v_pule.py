# -*- coding: utf-8 -*-
"""Почему клиники доходят до генерации, если медицина в минусе.

Предклассификатор на прогоне КЦ срезал 166 компаний, и в хвосте списка —
сплошь клиники, стоматологии и диагностика. Владелец убрал медицину ещё
19.08 («давай медицину в минус»), значит фильтр их не ловит. Смотрим, по
какому признаку он судит и что стоит у этих компаний.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.target_gate import МИНУС_ОКВЭД, минус_класс          # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
срезаны = []
for s in io.open(ЖУРНАЛ, encoding="utf-8"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    if z.get("этап") == "предкласс_отсев":
        срезаны.append(str(z.get("inn")))
срезаны = срезаны[-60:]
print(f"минус-ОКВЭД в гейте: {МИНУС_ОКВЭД}")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
счёт = Counter()
примеры = []
for инн in срезаны:
    with store._lock:
        r = store._conn.execute(
            "SELECT company_name, okved FROM recipients WHERE inn=? LIMIT 1",
            (инн,)).fetchone()
    if not r:
        счёт["нет карточки"] += 1
        continue
    имя, оквэд = r["company_name"] or "", str(r["okved"] or "")
    мед_по_имени = any(w in имя.upper() for w in (
        "КЛИНИК", "МЕДИЦ", "СТОМАТОЛОГ", "ДИАГНОСТИК", "ЗДОРОВЬ",
        "МЕДЦЕНТР", "МЦ ", "КДЦ", "ДЕНТ", "ГЛАЗА", "САНАТОРИ"))
    ловится = bool(минус_класс(оквэд, имя))
    if мед_по_имени and not ловится:
        счёт["МЕДИЦИНА, фильтр НЕ ловит"] += 1
        if len(примеры) < 12:
            примеры.append((инн, имя[:44], оквэд[:52]))
    elif мед_по_имени:
        счёт["медицина, фильтр ловит"] += 1
    else:
        счёт["не медицина"] += 1

for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
print("\n== кого фильтр пропускает ==")
for инн, имя, оквэд in примеры:
    print(f"  {инн}  {имя:<46} ОКВЭД {оквэд}")
