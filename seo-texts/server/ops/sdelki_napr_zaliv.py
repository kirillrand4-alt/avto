# -*- coding: utf-8 -*-
"""Залить активные сделки по направлениям (владелец 14.10) и выложить модуль заслона.

1) модуль sender/sdelki_napr.py: копия из server/ops/sdelki_napr_mod.py в
   C:\\sender\\sender\\sdelki_napr.py (бэкап, если был другой);
2) таблица sender.db/sdelki_napr из sdelki-napr-1410.json (дроп) — целиком
   заменяется свежей выгрузкой; журнал _ops/sdelki-napr.jsonl (fsync);
3) свод: сколько писем в очереди/расписании попадает под запрет.

    sdelki_napr_zaliv.py [--primenit]
"""
import filecmp
import io
import json
import os
import shutil
import sqlite3
import sys
import time
from collections import Counter

ПРИМ = "--primenit" in sys.argv
МОД_ИСТ = r"C:\sender\server\ops\sdelki_napr_mod.py"
МОД = r"C:\sender\sender\sdelki_napr.py"
д = json.load(io.open(r"C:\seostat\drop\drop-storage\sdelki-napr-1410.json", encoding="utf-8"))
print("ИНН с активной сделкой: %d" % len(д))
if ПРИМ:
    if os.path.exists(МОД) and not filecmp.cmp(МОД, МОД_ИСТ, shallow=False):
        shutil.copy2(МОД, МОД + ".bak-%d" % int(time.time()))
    shutil.copy2(МОД_ИСТ, МОД)
    print("модуль выложен: %s" % МОД)
sys.path.insert(0, r"C:\sender")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=60)
if ПРИМ:
    from sender.sdelki_napr import СХЕМА
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with c:
        c.execute(СХЕМА)
        c.execute("DELETE FROM sdelki_napr")
        c.executemany("INSERT INTO sdelki_napr (inn, meyer, kc, sc, detali, ts) VALUES (?,?,?,?,?,?)",
                      [(inn, int(bool(v["meyer"])), int(bool(v["kc"])), int(bool(v["sc"])),
                        json.dumps({k: v[k][:3] for k in ("meyer", "kc", "sc") if v[k]}, ensure_ascii=False), ts)
                       for inn, v in д.items()])
    with io.open(r"C:\sender\_ops\sdelki-napr.jsonl", "a", encoding="utf-8") as ж:
        ж.write(json.dumps({"ts": ts, "inn": len(д)}, ensure_ascii=False) + "\n")
        ж.flush()
        os.fsync(ж.fileno())
    print("в sdelki_napr: %d" % c.execute("SELECT count(*) FROM sdelki_napr").fetchone()[0])
# свод по очереди и расписанию
камп = {}
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.company_card import campaign_division  # noqa: E402
store = Store(r"C:\sender\sender.db")
св = Counter()
for mid, st, cid, inn in c.execute(
        "SELECT m.id, m.status, m.campaign_id, r.inn FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "WHERE m.status IN ('pending_review','approved','scheduled')"):
    if cid not in камп:
        cc = store.get_campaign(cid)
        камп[cid] = campaign_division(cc) if cc else None
    div = камп[cid]
    v = д.get("".join(ч for ч in str(inn or "") if ч.isdigit()))
    if v and div in ("meyer", "kc") and v[div]:
        св["%s: под запретом (%s)" % (st, div)] += 1
print("письма под новым запретом: %s" % dict(св))
print("=== СДЕЛКИ ПО НАПРАВЛЕНИЯМ: %s ===" % ("ПРИМЕНЕНО" if ПРИМ else "сухой прогон"))
