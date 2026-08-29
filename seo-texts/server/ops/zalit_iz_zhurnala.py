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

db = sqlite3.connect(D.ENR, timeout=300)
db.execute("PRAGMA busy_timeout=300000")
db.executescript(D.DDL)
было = db.execute("SELECT COUNT(*) FROM requisites "
                  " WHERE COALESCE(ogrn,'')<>''").fetchone()[0]
есть = {str(r[0]).strip() for r in db.execute(
    "SELECT inn FROM requisites WHERE COALESCE(ogrn,'')<>''")}
надо = [d for и, d in строки.items() if и not in есть]
print("уже в базе: %d, доливаем: %d" % (было, len(надо)))
залито = ошибок = 0
t0 = time.time()
for n, d in enumerate(надо, 1):
    try:
        db.execute("insert or replace into requisites ({}) values ({})".format(
            ",".join(D.FIELDS), ",".join("?" for _ in D.FIELDS)),
            [d.get(f) for f in D.FIELDS])
        залито += 1
    except sqlite3.OperationalError as ex:
        ошибок += 1
        if "locked" in str(ex).lower():
            time.sleep(3.0)
    if n % 200 == 0:
        db.commit()
try:
    db.commit()
except sqlite3.OperationalError:
    ошибок += 1
стало = db.execute("SELECT COUNT(*) FROM requisites "
                   " WHERE COALESCE(ogrn,'')<>''").fetchone()[0]
db.close()
print(json.dumps({"залито": залито, "ошибок": ошибок, "было": было,
                  "стало": стало, "секунд": round(time.time() - t0, 1)},
                 ensure_ascii=False))
