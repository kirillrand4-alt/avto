# -*- coding: utf-8 -*-
"""Расход без писем: доказать или снять обвинение, а не рассуждать.

Я заявил владельцу, что нажатие кнопки «Сгенерировать в очередь» тратило
деньги провайдера и не давало писем. Замерено из этого было ровно одно:
candidates(10, 14) идёт 403 секунды. Остальное - вывод, а вывод в отчёт
владельцу без проверки идти не должен.

Проверяемый след есть. Гейт рода деятельности (TargetGate) на каждую
несуженную компанию зовёт провайдера ДВУМЯ линзами и КАЖДЫЙ вердикт пишет
в enrich.db/target_verdicts со временем (ts) и пометкой источника
(source='ai_quota' - значит звали из отбора кандидатов). Письма пишутся
позже и ложатся в confirm_reviews со своим created_at.

Значит вопрос решается сопоставлением двух временных рядов: были ли минуты,
когда вердикты писались (деньги шли), а строки очереди не появлялись.

Печатаем поминутно за сегодня: вердиктов гейта столько-то, писем в очереди
столько-то.

    python zapusk_svoego_skripta.py ops/rashod_bez_pisem_dokazatelstvo.py
"""
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

# ВЕРДИКТЫ ЛЕЖАТ В sender.db, А НЕ В enrich.db. Первая редакция скрипта
# искала их в enrich.db и получила «no such table» - то есть ноль вердиктов,
# и по нему я чуть не снял обвинение с кнопки. AiQuota._gate собирает
# TargetGate на self._db_path, а это база панели.
ГЕЙТ_БАЗА = r"C:\sender\sender.db"
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

# --- вердикты гейта: когда и по чьей просьбе ------------------------------ #
по_минутам_гейт = Counter()
источники = Counter()
всего_вердиктов = 0
if os.path.exists(ГЕЙТ_БАЗА):
    con = sqlite3.connect(f"file:{ГЕЙТ_БАЗА}?mode=ro", uri=True, timeout=20)
    try:
        for inn, verdict, source, ts in con.execute(
                "SELECT inn, verdict, source, ts FROM target_verdicts"):
            всего_вердиктов += 1
            t = str(ts or "")
            if not t.startswith("2026-08-17"):
                continue
            источники[str(source or "")] += 1
            по_минутам_гейт[t[11:16]] += 1
    except Exception as ex:                                     # noqa: BLE001
        print("target_verdicts не прочитались:", str(ex)[:150])
    finally:
        con.close()
else:
    print("база гейта не найдена")

# --- письма очереди: когда появились -------------------------------------- #
по_минутам_письма = Counter()
with store._lock:
    for (созд,) in store._conn.execute(
            "SELECT created_at FROM confirm_reviews"):
        t = str(созд or "")
        if t.startswith("2026-08-17"):
            по_минутам_письма[t[11:16]] += 1

print(f"вердиктов гейта всего в базе: {всего_вердиктов}")
print(f"из них сегодня: {sum(по_минутам_гейт.values())}, "
      f"по источникам: {dict(источники)}")
print(f"писем в очереди создано сегодня: {sum(по_минутам_письма.values())}")

минуты = sorted(set(по_минутам_гейт) | set(по_минутам_письма))
print("\nвремя  вердиктов_гейта  писем_в_очередь")
тратили_без_писем = 0
for м in минуты:
    г = по_минутам_гейт.get(м, 0)
    п = по_минутам_письма.get(м, 0)
    метка = ""
    if г and not п:
        метка = "  <- платили, письма не появлялись"
        тратили_без_писем += г
    print(f"{м}  {г:>14}  {п:>15}{метка}")

print(f"\nвердиктов, выписанных в минуты БЕЗ единого письма: "
      f"{тратили_без_писем}")
print("Вердикт = два вызова провайдера на компанию (продавец + скептик), "
      "если он не был закэширован раньше.")
