# -*- coding: utf-8 -*-
"""Долить карточки из журнала добора в enrich.db, когда база свободна.

Журнал (sdelki-rekvizity.jsonl, fsync) — durable-запись прогона; база может
быть занята соседними службами. Этот прогон читает журнал и доливает всё, чего
в requisites ещё нет. Идемпотентен: insert or replace по ИНН.
"""
import io
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender\_ops")
import _ops_dadata_req as D                                        # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\sdelki-rekvizity.jsonl"
if not os.path.exists(ЖУРНАЛ):
    print("журнала нет")
    raise SystemExit(0)

строки = {}
битых = 0
for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="ignore"):
    с = с.strip()
    if not с:
        continue
    try:
        d = json.loads(с)
    except Exception:                                              # noqa: BLE001
        битых += 1
        continue
    и = str(d.get("inn") or "").strip()
    if и:
        строки[и] = d               # последняя запись по ИНН побеждает
print("в журнале записей: %d (битых строк %d)" % (len(строки), битых))

# enrich.db в WAL: читатели не мешают, мешает ДРУГОЙ ПИСАТЕЛЬ — служба обзвона
# пишет почти непрерывно (файл -wal рос до 463 МБ). Долгое ожидание тут вредно:
# прогон с busy_timeout 180 с висел и не двигался. Берём короткие попытки и
# много заходов — вклиниваемся в паузы между чужими транзакциями.
БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 1500.0
ПАЧКА = 25
db = sqlite3.connect(D.ENR, timeout=30)
# Замер: 12 коротких попыток за 45 секунд — все отказаны, при этом счётчики
# таблиц не растут. Значит сосед держит лок долгими UPDATE-ами, а не вставками.
# Ждём по 12 секунд и берём мелкие пачки: так шанс вклиниться выше.
db.execute("PRAGMA busy_timeout=12000")
db.executescript(D.DDL)
было = db.execute("SELECT COUNT(*) FROM requisites "
                  " WHERE COALESCE(ogrn,'')<>''").fetchone()[0]
есть = {str(r[0]).strip() for r in db.execute(
    "SELECT inn FROM requisites WHERE COALESCE(ogrn,'')<>''")}
надо = [d for и, d in строки.items() if и not in есть]
print("уже в базе: %d, доливаем: %d" % (было, len(надо)))

t0 = time.time()
залито = попыток = отказов = 0
i = 0
while i < len(надо) and time.time() - t0 < БЮДЖЕТ:
    пачка = надо[i:i + ПАЧКА]
    попыток += 1
    try:
        db.execute("BEGIN IMMEDIATE")
        for d in пачка:
            db.execute(
                "insert or replace into requisites ({}) values ({})".format(
                    ",".join(D.FIELDS), ",".join("?" for _ in D.FIELDS)),
                [d.get(f) for f in D.FIELDS])
        db.commit()
        залито += len(пачка)
        i += ПАЧКА
    except sqlite3.OperationalError as ex:
        try:
            db.rollback()
        except Exception:                                          # noqa: BLE001
            pass
        if "locked" not in str(ex).lower() and "busy" not in str(ex).lower():
            raise
        отказов += 1
        time.sleep(1.5)
    if попыток % 20 == 0:
        print("   %d/%d залито, отказов %d, %.0f с"
              % (залито, len(надо), отказов, time.time() - t0), flush=True)
стало = db.execute("SELECT COUNT(*) FROM requisites "
                   " WHERE COALESCE(ogrn,'')<>''").fetchone()[0]
db.close()
print(json.dumps({"залито": залито, "осталось": len(надо) - залито,
                  "отказов_блокировки": отказов, "было": было, "стало": стало,
                  "секунд": round(time.time() - t0, 1)}, ensure_ascii=False))
