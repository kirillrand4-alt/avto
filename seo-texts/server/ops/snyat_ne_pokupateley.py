# -*- coding: utf-8 -*-
"""Снять из очереди карточки компаний, которым гейт заходов уже вынес
«не покупатель».

Дыра в постановке копий: cs.submit() проверяет стоп-лист, недоставимость и
повторный контакт, но НЕ смотрит target_verdicts — гейт заходов работает на
этапе генерации, а копия письма генерацию минует. «Праксэа РУС» гейт назвал
конкурентом («сами производят кислород и азот»), а копия всё равно легла в
очередь.
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
СЛЕД = r"C:\sender\_ops\vtorye-snyatye.jsonl"

партия = {}
for с in io.open(r"C:\sender\_ops\vtorye-adresa.jsonl", encoding="utf-8"):
    d = json.loads(с)
    партия[int(d["review"])] = str(d["inn"])
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
зн = ",".join("?" * len(партия))
строки = c.execute(
    "SELECT cr.id, cr.inn, cr.email, r.company_name, t.verdict, t.pochemu "
    "  FROM confirm_reviews cr "
    "  LEFT JOIN recipients r ON r.id = cr.recipient_id "
    "  JOIN target_verdicts t ON t.inn = cr.inn "
    " WHERE cr.id IN (%s) AND cr.status='pending' "
    "   AND t.verdict = 'не покупатель'" % зн, list(партия)).fetchall()
c.close()
print("в очереди с вердиктом гейта «не покупатель»: %d" % len(строки))
for r in строки:
    print("   rev %-6s %-26s %s" % (r["id"], str(r["email"])[:26],
                                    str(r["company_name"] or "")[:34]))
    print("      гейт: %s" % str(r["pochemu"] or "")[:104])
if not КАТИТЬ or not строки:
    raise SystemExit(0)

from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.wiring import build_deps                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = build_deps(cfg, store, dry_run=True).confirm
итог = Counter()
поток = io.open(СЛЕД, "a", encoding="utf-8")
for r in строки:
    почему = str(r["pochemu"] or "")[:150]
    try:
        ок = cs.skip(int(r["id"]), reason="гейт заходов: не покупатель — " + почему,
                     operator="сверка с гейтом 28.08")
        итог["снято" if ок else "не в pending"] += 1
        if ок:
            поток.write(json.dumps(
                {"review": int(r["id"]), "inn": str(r["inn"]), "email": r["email"],
                 "prichina": "гейт: не покупатель — " + почему,
                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
    except Exception as ex:                                       # noqa: BLE001
        итог["ошибка: " + str(ex)[:44]] += 1
поток.close()
print("")
for к, n in итог.most_common():
    print("   %-30s %4d" % (к, n))
