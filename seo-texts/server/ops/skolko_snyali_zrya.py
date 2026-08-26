# -*- coding: utf-8 -*-
"""Сколько снятых «никуда» на самом деле имеют производство или добычу.

Владелец 26.08 поймал две ошибки подряд: золотодобыче нужен компрессор, а
поставщика овощей для HoReCa стоит проверить — там бывает мойка,
калибровка и фасовка. Смотрим, насколько это единичные случаи.
"""
import io
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

ЦЕХ = re.compile(r"производств|изготовл|выпускае|собственн\w+ марк", re.I)
ДОБЫЧА = re.compile(r"добыч|руд[аыу]|рудник|флотац|дроблен|обогатительн|"
                    r"карьер|шахт|гок\b|щебен|обогащен", re.I)
ЕДА = re.compile(r"специ|пряност|приправ|донат|конфет|печен|снек|орех|"
                 r"сухофрукт|кофе|чай|круп|мук[аи]|зерн|овощ|фрукт|"
                 r"фасовк|калибровк|мойк[аи]|сортиров", re.I)

итог = {}
for с in io.open(r"C:\sender\_ops\predprosev-meyer.jsonl",
                 encoding="utf-8", errors="replace"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:                                         # noqa: BLE001
        continue
    if з.get("инн"):
        итог[з["инн"]] = з

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

свод = Counter()
примеры = {"цех в паспорте": [], "добыча": [], "еда в паспорте": []}
for з in итог.values():
    if з.get("вердикт") != "никуда":
        continue
    свод["всего снятых"] += 1
    try:
        п = q._pasport_dlya_geyta(з["инн"]) or ""
    except Exception:                                         # noqa: BLE001
        п = ""
    if not п:
        свод["без паспорта"] += 1
        continue
    метки = []
    if ЦЕХ.search(п):
        метки.append("цех в паспорте")
    if ДОБЫЧА.search(п):
        метки.append("добыча")
    if ЕДА.search(п):
        метки.append("еда в паспорте")
    if not метки:
        свод["паспорт без признаков производства"] += 1
        continue
    for м in метки:
        свод[м] += 1
        if len(примеры[м]) < 8:
            примеры[м].append((з.get("имя"), з.get("почему"), п))
    свод["спорных всего"] += 1

print("=== снятые «никуда» под лупой ===")
for имя, n in свод.most_common():
    print("   %-38s %d" % (имя, n))
for м, спис in примеры.items():
    if not спис:
        continue
    print("")
    print("--- %s ---" % м)
    for имя, почему, п in спис:
        print("   %s" % str(имя)[:56])
        print("      вердикт: %s" % str(почему)[:110])
        print("      паспорт: %s" % " ".join(str(п).split())[:150])
