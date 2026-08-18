# -*- coding: utf-8 -*-
"""Как теперь выглядит письмо в ленте лида — до и после разбора HTML.

Проверяем на ЖИВОМ письме, а не на выдуманном: берём последний входящий
ответ и печатаем сырое тело и то, что увидит панель.

    python zapusk_svoego_skripta.py ops/lenta_lida_kak_vyglyadit.py [id_лида]
"""
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.pismo_v_tekst import v_tekst                         # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряд = store._conn.execute(
        "SELECT id, recipient_id, event_ts, detail_json FROM events "
        "WHERE event_type IN ('reply','reply_auto') "
        "ORDER BY event_ts DESC LIMIT 3").fetchall()
print(f"последних входящих ответов: {len(ряд)}\n")
for eid, rid, ts, dj in ряд:
    d = json.loads(dj or "{}")
    сырое = str(d.get("snippet") or "")
    print("=" * 72)
    print(f"событие {eid}, получатель {rid}, {str(ts)[:19]}")
    print(f"--- СЫРОЕ ({len(сырое)} знаков), первые 400:")
    print(сырое[:400])
    т = v_tekst(сырое)
    print(f"\n--- КАК ПОКАЖЕТ ПАНЕЛЬ ({len(т)} знаков), первые 700:")
    print(т[:700])

    # и то же самое через настоящую ленту диалога
    try:
        лента = store.dialog_thread(int(rid))
        вх = [x for x in лента if x.get("direction") == "in"]
        if вх:
            print(f"\n--- через dialog_thread (последний входящий), 300 знаков:")
            print(str(вх[-1].get("body") or "")[:300])
    except Exception as ex:                                      # noqa: BLE001
        print("dialog_thread:", str(ex)[:120])
