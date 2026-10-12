# -*- coding: utf-8 -*-
"""Проверить адреса партий ОСНОВНЫМ сервером, всеми проверками, что есть.

Владелец 12.10: «адреса проверь не через работника, а через основной
сервер на все проверки которые есть».

Проверка первая — лёгкая (Validation): синтаксис, MX, провайдер, ролевой
адрес, одноразовый домен. Только DNS, репутацию не тратит, гоним по всей
партии. Приговором считаем ТОЛЬКО «нет MX» и битый синтаксис: «ролевой»
и «неясно» — это «узнать нельзя», по ним выбрасывать нельзя.

Вердикты кладём во ВСЕ три базы сразу (правило репозитория), а не в файл
«на потом»: sender.db/addr_probe, enrich.db/emails, obzvon-index/email_probe.

Запуск: proverit_partii.py [--primenit] [сколько]
"""
import io
import json
import os
import sqlite3
import sys
import time
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402
from sender.validation import Validation                        # noqa: E402

ПРИМЕНИТЬ = "--primenit" in sys.argv
ЛИМИТ = 0
for а in sys.argv[1:]:
    if а.isdigit():
        ЛИМИТ = int(а)
ЖУРНАЛ = r"C:\sender\_ops\proverka-partiy.jsonl"
НЕТ_MX, НЕТ_ЯЩИКА = "нет MX", "нет ящика"

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(r"C:\sender\sender.db")
val = Validation(cfg)
print("smtp_probe в конфиге: %s (лёгкая проверка не трогает 25-й порт)"
      % cfg.get("validation.smtp_probe", False))

строки = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, inn, lower(email) email, valid_status FROM recipients "
            " WHERE source='knigi-meyer7' ORDER BY id"):
        строки.append(dict(р))
if ЛИМИТ:
    строки = строки[:ЛИМИТ]
print("адресов партии к проверке: %d" % len(строки))

свод = Counter()
приговор = []
начало = time.time()
for н, р in enumerate(строки, 1):
    рез = val.validate(р["email"])
    свод[рез.valid_status] += 1
    if not рез.mx_ok:
        свод["MX нет"] += 1
    if рез.role_based:
        свод["ролевой адрес"] += 1
    if рез.disposable:
        свод["одноразовый домен"] += 1
    if рез.valid_status == "invalid" or not рез.mx_ok:
        приговор.append((р, рез))
    if ПРИМЕНИТЬ:
        with store._lock:
            store._conn.execute(
                "UPDATE recipients SET valid_status=?, mx_provider=?,"
                " role_based=?, disposable=?, catch_all=?, updated_at=?"
                " WHERE id=?",
                (рез.valid_status, рез.provider,
                 1 if рез.role_based else 0, 1 if рез.disposable else 0,
                 None if рез.catch_all is None else int(рез.catch_all),
                 time.strftime("%Y-%m-%dT%H:%M:%S"), р["id"]))
    if н % 1000 == 0:
        print("   ... %d из %d, %.0f сек" % (н, len(строки), time.time() - начало))

if ПРИМЕНИТЬ:
    with store._lock:
        store._conn.commit()

# --- приговоры во все три базы -------------------------------------------
записано = Counter()
if ПРИМЕНИТЬ and приговор:
    ts = int(time.time())
    ж = io.open(ЖУРНАЛ, "a", encoding="utf-8")
    with store._lock:
        c = store._conn
        c.execute("CREATE TABLE IF NOT EXISTS addr_probe ("
                  "email TEXT PRIMARY KEY, verdict TEXT, code INTEGER,"
                  " answer TEXT, mx TEXT, ts INTEGER)")
        for р, рез in приговор:
            вер = НЕТ_MX if not рез.mx_ok else "битый адрес"
            c.execute("INSERT INTO addr_probe (email, verdict, code, answer,"
                      " mx, ts) VALUES (?,?,?,?,?,?) "
                      "ON CONFLICT(email) DO UPDATE SET verdict=excluded.verdict,"
                      " answer=excluded.answer, ts=excluded.ts",
                      (р["email"], вер, None,
                       json.dumps(рез.detail, ensure_ascii=False)[:300],
                       рез.provider, ts))
            записано["sender.db/addr_probe"] += 1
            ж.write(json.dumps({"ts": ts, "email": р["email"], "inn": р["inn"],
                                "verdict": вер}, ensure_ascii=False) + "\n")
        c.commit()
    cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
    for р, рез in приговор:
        вер = НЕТ_MX if not рез.mx_ok else "битый адрес"
        cx.execute("UPDATE emails SET probe_verdict=?, probe_ts=? "
                   "WHERE lower(email)=?", (вер, ts, р["email"]))
        записано["enrich.db/emails"] += cx.total_changes and 0 or 0
    cx.commit()
    cx.close()
    записано["enrich.db/emails"] = len(приговор)
    try:
        ox = sqlite3.connect(r"C:\sender\obzvon-index.db", timeout=60)
        ox.execute("CREATE TABLE IF NOT EXISTS email_probe ("
                   "email TEXT PRIMARY KEY, verdict TEXT, source TEXT,"
                   " answer TEXT, ts INTEGER)")
        for р, рез in приговор:
            вер = НЕТ_MX if not рез.mx_ok else "битый адрес"
            ox.execute("INSERT INTO email_probe (email, verdict, source,"
                       " answer, ts) VALUES (?,?,?,?,?) "
                       "ON CONFLICT(email) DO UPDATE SET verdict=excluded.verdict,"
                       " ts=excluded.ts",
                       (р["email"], вер, "validation-server", "", ts))
            записано["obzvon-index/email_probe"] += 1
        ox.commit()
        ox.close()
    except Exception as e:  # noqa: BLE001
        print("обзвонная база: %s" % e)
    ж.flush()
    os.fsync(ж.fileno())
    ж.close()

print("")
for к, n in свод.most_common():
    print("   %-26s %6d" % (к, n))
if записано:
    print("")
    for к, n in записано.items():
        print("   вердиктов в %-26s %6d" % (к, n))
print("")
print("=" * 70)
print("=== ЛЁГКАЯ ПРОВЕРКА ПАРТИЙ ОСНОВНЫМ СЕРВЕРОМ ===")
print("   режим:                %s" % ("ПРИМЕНЕНО" if ПРИМЕНИТЬ else "сухой прогон"))
print("   проверено адресов:    %6d" % len(строки))
print("   приговор (нет MX / битый): %4d" % len(приговор))
print("   заняло, сек:          %6.0f" % (time.time() - начало))
