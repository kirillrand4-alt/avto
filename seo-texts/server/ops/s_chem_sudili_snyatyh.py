# -*- coding: utf-8 -*-
"""Чем на самом деле располагала модель по каждому снятому «никуда».

Прошлый замер («судили по тексту сайта: 11») был неверен: он искал
site_text в extra получателя, а паспорт сайта приходит из enrich.db через
_pasport_dlya_geyta и в extra не лежит. Считаем то, что реально уходило в
вопрос.
"""
import io
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

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
голые = []
for з in итог.values():
    if з.get("вердикт") != "никуда":
        continue
    rec = store.get_recipient(int(з["rid"]))
    if rec is None:
        свод["карточки нет"] += 1
        continue
    try:
        паспорт = q._pasport_dlya_geyta(з["инн"]) or ""
    except Exception:                                         # noqa: BLE001
        паспорт = ""
    try:
        занятие = str(q._request(rec).get("activity") or "")
    except Exception:                                         # noqa: BLE001
        занятие = ""
    if паспорт and занятие:
        свод["паспорт сайта + занятие"] += 1
    elif паспорт:
        свод["паспорт сайта"] += 1
    elif занятие:
        свод["только занятие"] += 1
    else:
        свод["только название и ОКВЭД"] += 1
        голые.append(з)

print("=== чем располагала модель по снятым ===")
for имя, n in свод.most_common():
    print("   %-28s %d" % (имя, n))
print("")
print("=== снятые ВСЛЕПУЮ (ни паспорта, ни занятия): %d ===" % len(голые))
for з in голые[:25]:
    print("   %-40s %s" % (str(з.get("имя"))[:40], str(з.get("почему"))[:90]))
