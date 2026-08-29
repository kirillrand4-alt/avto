# -*- coding: utf-8 -*-
"""Добрать карточки ЕГРЮЛ по компаниям со сделкой, которых нет в наших базах.

3040 из 3749 проверенных покупателей не лежат ни в обзвоне, ни в обогащении —
конвейер их не видит вовсе. Первый шаг: реквизиты, ОКВЭД, регион, статус.
Берём готовый инструмент _ops/_ops_dadata_req.py (DaData findById/party,
таблица enrich.db.requisites) и подставляем свой список ИНН.

Порядок: сперва «невидимые», потом остальные сделки. DURABILITY: commit каждые
25 записей + журнал с fsync, прогон резюмируемый — уже добранные пропускаем.

Запуск: python sdelki_dadata.py [бюджет_сек]
"""
import json
import os
import sqlite3
import sys
import time
import urllib.error

sys.path.insert(0, r"C:\sender\_ops")
import _ops_dadata_req as D                                        # noqa: E402

БЮДЖЕТ = float(sys.argv[1]) if len(sys.argv) > 1 else 900.0
СЕНДЕР = r"C:\sender\sender.db"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ЖУРНАЛ = r"C:\sender\_ops\sdelki-rekvizity.jsonl"


def цифры(з):
    return "".join(c for c in str(з or "") if c.isdigit())


c = sqlite3.connect("file:%s?mode=ro" % СЕНДЕР, uri=True, timeout=60)
сделки = {цифры(r[0]) for r in c.execute(
    "SELECT value FROM suppression WHERE reason='deal_in_progress' "
    "  AND scope='inn'")}
сделки.discard("")
c.close()

o = sqlite3.connect("file:%s?mode=ro" % ОБЗВОН, uri=True, timeout=60)
обзвон = {цифры(r[0]) for r in o.execute("SELECT inn FROM obzvon")}
o.close()

db = sqlite3.connect(D.ENR, timeout=60)
db.executescript(D.DDL)
есть = {цифры(r[0]) for r in db.execute(
    "SELECT inn FROM requisites WHERE COALESCE(ogrn,'') <> ''")}
знаем = {цифры(r[0]) for r in db.execute("SELECT inn FROM companies")}

невидимые = sorted(сделки - обзвон - знаем - есть)
остальные = sorted((сделки - есть) - set(невидимые))
todo = невидимые + остальные
print("компаний со сделкой: %d" % len(сделки))
print("   уже с реквизитами: %d" % len(сделки & есть))
print("   в очереди сейчас:  %d (невидимых %d, прочих %d)"
      % (len(todo), len(невидимые), len(остальные)))

os.makedirs(os.path.dirname(ЖУРНАЛ), exist_ok=True)
jl = open(ЖУРНАЛ, "a", encoding="utf-8")
t0 = time.time()
ok = miss = err = 0
последняя = None
for n, inn in enumerate(todo, 1):
    if time.time() - t0 > БЮДЖЕТ:
        break
    try:
        d = D.lookup(inn)
    except urllib.error.HTTPError as e:
        err += 1
        последняя = "HTTP %s на %s" % (e.code, inn)
        if e.code in (403, 429):
            break
        time.sleep(1.0)
        continue
    except Exception as e:                                         # noqa: BLE001
        err += 1
        последняя = "%s: %s" % (type(e).__name__, str(e)[:80])
        time.sleep(1.0)
        continue
    if not d:
        miss += 1
        row = {"inn": inn, "src": "dadata", "status": None}
    else:
        row = D.parse(d)
        row["inn"] = row.get("inn") or inn
        row["src"] = "dadata"
        ok += 1
    row["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    row["raw"] = json.dumps(d, ensure_ascii=False) if d else None
    db.execute("insert or replace into requisites ({}) values ({})".format(
        ",".join(D.FIELDS), ",".join("?" for _ in D.FIELDS)),
        [row.get(f) for f in D.FIELDS])
    jl.write(json.dumps({k: row.get(k) for k in D.FIELDS if k != "raw"},
                        ensure_ascii=False) + "\n")
    if n % 25 == 0:
        db.commit()
        jl.flush()
        os.fsync(jl.fileno())
    time.sleep(0.14)
db.commit()
jl.flush()
os.fsync(jl.fileno())
всего = db.execute(
    "SELECT COUNT(*) FROM requisites WHERE COALESCE(ogrn,'') <> ''").fetchone()[0]
db.close()
jl.close()
print(json.dumps({
    "в_очереди_было": len(todo), "получено": ok,
    "нет_в_ЕГРЮЛ": miss, "ошибок": err, "последняя_ошибка": последняя,
    "всего_в_requisites_с_ОГРН": всего, "секунд": round(time.time() - t0, 1),
    "осталось_по_сделкам": len(todo) - ok - miss}, ensure_ascii=False))
