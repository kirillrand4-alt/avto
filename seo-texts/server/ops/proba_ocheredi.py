# -*- coding: utf-8 -*-
"""Проба адресов, которые стоят в очереди (scheduled / pending_review) без
вердикта, — и сразу снятие писем с приговором.

13.10: два из трёх утренних отбоев (КИПРЕЙ, Осинниковский маслозавод) — адреса
mail.ru/bk.ru, до которых общая проба ещё не дошла: письмо ушло непроверенным.
Проверка без применения бесполезна (CLAUDE.md) — вердикт идёт в три базы и
письмо с «нет ящика»/«нет MX» снимается в том же прогоне.

    proba_ocheredi.py --zapusk   — в фоне (отвязанный процесс)
    proba_ocheredi.py --rabota   — сама работа
    proba_ocheredi.py            — ход
"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone

ХОД = r"C:\sender\_ops\proba-ocheredi.json"
ЖУРНАЛ = r"C:\sender\_ops\smtp-proba-partiy.jsonl"
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru",
           "ya.ru", "gmail.com", "rambler.ru"}
ПАУЗА = 20.0
ПРИГОВОР = ("нет ящика", "нет MX")
sys.path.insert(0, r"C:\sender")

if "--zapusk" in sys.argv:
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"],
                         cwd=r"C:\sender", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000008 | 0x00000200)
    time.sleep(10)
    print("запущено, pid %d, жив %s" % (п.pid, п.poll() is None))
    print("=== ПРОБА ОЧЕРЕДИ: ЗАПУЩЕНА ===")
    sys.exit(0)

if "--rabota" in sys.argv:
    from sender.addr_probe import build_addr_probe
    from sender.config import Config
    from sender.store import Store
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    _п = build_addr_probe(store, cfg)
    проба = getattr(_п, "probe", None) or getattr(_п, "probe_")
    проба.per_domain = 10 ** 6
    c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
    c.row_factory = sqlite3.Row
    очередь = {}
    for р in c.execute("SELECT m.id, lower(r.email) e, r.inn FROM messages m JOIN recipients r "
                       "ON r.id=m.recipient_id WHERE m.status IN ('scheduled','pending_review')"):
        if not проба.cached(р["e"]):
            очередь.setdefault((р["e"], р["inn"]), []).append(р["id"])
    ход = {"старт": time.strftime("%H:%M:%S"), "всего": len(очередь), "проверено": 0,
           "вердикты": {}, "снято_писем": 0}

    def отметить():
        with io.open(ХОД, "w", encoding="utf-8") as ф:
            json.dump(ход, ф, ensure_ascii=False)
            ф.flush()
            os.fsync(ф.fileno())

    отметить()
    посл = {}
    for (адрес, инн), письма in sorted(очередь.items(), key=lambda x: x[0][0].rsplit("@", 1)[-1] in КРУПНЫЕ):
        дом = адрес.rsplit("@", 1)[-1]
        if дом in КРУПНЫЕ:
            ждать = ПАУЗА - (time.monotonic() - посл.get(дом, -1e9))
            if ждать > 0:
                time.sleep(ждать)
            посл[дом] = time.monotonic()
        try:
            рез = проба.probe(адрес)
        except Exception as е:  # noqa: BLE001
            рез = {"verdict": "неясно", "answer": str(е)[:200]}
        вер = str(рез.get("verdict") or "неясно")
        ts = int(time.time())
        ход["проверено"] += 1
        ход["вердикты"][вер] = ход["вердикты"].get(вер, 0) + 1
        # три базы: sender.db/addr_probe пишет сама проба; enrich и обзвон — здесь
        try:
            cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
            cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=?, probe_answer=? "
                       "WHERE lower(email)=?", (вер, ts, str(рез.get("answer") or "")[:300], адрес))
            cx.commit()
            cx.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
            ox.execute("CREATE TABLE IF NOT EXISTS email_probe (email TEXT PRIMARY KEY, verdict TEXT, "
                       "source TEXT, answer TEXT, ts INTEGER)")
            ox.execute("INSERT INTO email_probe (email, verdict, source, answer, ts) VALUES (?,?,?,?,?) "
                       "ON CONFLICT(email) DO UPDATE SET verdict=excluded.verdict, "
                       "answer=excluded.answer, ts=excluded.ts",
                       (адрес, вер, "smtp-server", str(рез.get("answer") or "")[:300], ts))
            ox.commit()
            ox.close()
        except Exception:  # noqa: BLE001
            pass
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
            ж.write(json.dumps({"ts": ts, "email": адрес, "inn": инн, "verdict": вер,
                                "istochnik": "ochered"}, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())
        if вер in ПРИГОВОР:
            т = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            with c:
                ход["снято_писем"] += c.executemany(
                    "UPDATE messages SET status='skipped', last_error=?, updated_at=? WHERE id=? "
                    "AND status IN ('scheduled','pending_review')",
                    [("снято 13.10: приговор пробы «%s»" % вер, т, м) for м in письма]).rowcount
        отметить()
    ход["финиш"] = time.strftime("%H:%M:%S")
    отметить()
    sys.exit(0)

try:
    ход = json.load(io.open(ХОД, encoding="utf-8"))
except Exception as е:  # noqa: BLE001
    print("хода нет: %s" % е)
    sys.exit(0)
print("старт %s, финиш %s | адресов %d, проверено %d, снято писем %d" % (
    ход["старт"], ход.get("финиш", "—"), ход["всего"], ход["проверено"], ход["снято_писем"]))
print("вердикты: %s" % ход["вердикты"])
print("=== ПРОБА ОЧЕРЕДИ: ХОД ===")
