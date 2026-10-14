# -*- coding: utf-8 -*-
"""Письма Meyer в очереди, которые заслон направлений блокирует: метка базы
обзвона = только kc, а наши проверки признали компанию покупателем Meyer
(вердикт «наш или нет» в enrich: мейер/оба). С --primenit дописываем к метке
obzvon.division «+meyer» (kc остаётся), старую метку — в резерв
_ops/meyer-v-metku-obzvona.jsonl (fsync). Без вердикта «мейер» не трогаем.

    meyer_v_metku_obzvona.py [--primenit]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402

ПРИМ = "--primenit" in sys.argv
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
from sender.company_card import ObzvonIndex, campaign_division  # noqa: E402
idx = ObzvonIndex(r"C:\sender\obzvon-index.db")
camp_div = campaign_division(store.get_campaign(14))
print("направление кампании 14: %s" % camp_div)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
c.row_factory = sqlite3.Row
e = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
o = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
o.row_factory = sqlite3.Row
св, к_правке = Counter(), {}
for р in c.execute("SELECT id, inn, campaign_id FROM confirm_reviews WHERE status='pending' AND campaign_id=14"):
    разр = idx.divisions(р["inn"])
    if not разр or camp_div in разр:
        continue
    инн = "".join(ч for ч in str(р["inn"] or "") if ч.isdigit())
    в = e.execute("SELECT verdikt_napr, verdikt_istochnik FROM companies WHERE inn=?", (инн,)).fetchone()
    napr, ист = (в or (None, None))
    if napr in ("мейер", "оба"):
        св["заблокировано, вердикт мейер (%s)" % ист] += 1
        стр = o.execute("SELECT division FROM obzvon WHERE inn=?", (инн,)).fetchone()
        if стр is not None:
            к_правке[инн] = стр["division"] or ""
    else:
        св["заблокировано, вердикт %s — не трогаем" % (napr or "нет")] += 1
print("свод: %s" % dict(св.most_common()))
print("компаний к дописке +meyer: %d" % len(к_правке))
if ПРИМ and к_правке:
    with io.open(r"C:\sender\_ops\meyer-v-metku-obzvona.jsonl", "a", encoding="utf-8") as ж:
        for инн, было in к_правке.items():
            ж.write(json.dumps({"inn": инн, "division_bylo": было, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                               ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    n = 0
    for инн, было in к_правке.items():
        части = [p for p in было.split("+") if p]
        if "meyer" not in части:
            части.append("meyer")
        n += o.execute("UPDATE obzvon SET division=? WHERE inn=?", ("+".join(части), инн)).rowcount
    o.commit()
    print("метка дописана: %d" % n)
print("=== MEYER В МЕТКУ ОБЗВОНА: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
