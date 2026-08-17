# -*- coding: utf-8 -*-
"""Довезти вердикты пробы в enrich.db - третью из трёх баз.

Проба с сервера проверила всю партию (827 адресов), вердикты легли в
addr_probe панели и в obzvon-index.db, а в обогащение - нет: функция поиска
базы вызывалась без пути к базе панели и вернула None. Правило «мёртвый
адрес выпадает из работы ОДИН раз» держится ровно на этой третьей записи:
отбор кандидатов делается из enrich.db, и без вердикта мёртвый адрес будет
всплывать в новых партиях снова и снова.

Берём вердикты из durable-журнала пробы, а не пере-проверяем адреса.
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                               # noqa: E402
from sender.probe_enrich import записать, найти                # noqa: E402

Ж = r"C:\sender\_ops\proba-partii-server.jsonl"
cfg = Config.load(r"C:\sender\sender.yaml")
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")

путь = найти(cfg, БАЗА)
print("база обогащения:", путь, "| есть:", bool(путь and os.path.exists(путь)))
if not путь:
    raise SystemExit("не нашлась - везти некуда")

вердикты, счёт = {}, Counter()
for s in (io.open(Ж, encoding="utf-8") if os.path.exists(Ж) else []):
    try:
        z = json.loads(s)
    except Exception:                                          # noqa: BLE001
        continue
    e = str(z.get("email") or "").strip().lower()
    if not e:
        continue
    вердикты[e] = {"email": e, "verdict": z.get("verdict"),
                   "answer": z.get("answer")}
    счёт[str(z.get("verdict"))] += 1

print(f"вердиктов в журнале пробы: {len(вердикты)}")
for k, n in счёт.most_common():
    print(f"  {k:<16} {n}")

итог = записать(путь, list(вердикты.values()))
print("\nв enrich.db:", итог)
