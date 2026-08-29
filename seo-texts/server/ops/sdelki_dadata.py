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
import io
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

# БАЗУ В ГОРЯЧЕМ ПУТИ НЕ ТРОГАЕМ ВОВСЕ. enrich.db надолго держат соседние
# службы обзвона; прогон с записью в базу за 1720 секунд обработал ТРИ записи —
# каждый commit висел на блокировке по 180 секунд и трижды повторялся. Durable
# здесь журнал с fsync, а в базу карточки доливает zalit_iz_zhurnala.py, когда
# она свободна. Читаем базу тоже только на чтение и с коротким ожиданием.
db = sqlite3.connect("file:%s?mode=ro" % D.ENR, uri=True, timeout=20)
db.execute("PRAGMA busy_timeout=15000")
try:
    есть = {цифры(r[0]) for r in db.execute(
        "SELECT inn FROM requisites WHERE COALESCE(ogrn,'') <> ''")}
    знаем = {цифры(r[0]) for r in db.execute("SELECT inn FROM companies")}
except sqlite3.OperationalError as ex:
    print("база занята (%s) — резюм только по журналу" % str(ex)[:40])
    есть, знаем = set(), set()
db.close()
# Журнал — вторая половина резюма: он пишется даже когда база недоступна.
if os.path.exists(ЖУРНАЛ):
    for с in io.open(ЖУРНАЛ, encoding="utf-8", errors="ignore"):
        с = с.strip()
        if not с:
            continue
        try:
            и = цифры(json.loads(с).get("inn"))
        except Exception:                                          # noqa: BLE001
            continue
        if и:
            есть.add(и)

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
    # ЖУРНАЛ ПЕРВЫМ, база — по возможности. enrich.db надолго берут соседние
    # службы (обзвон на 8012/8014), и busy_timeout не спасает: два прогона
    # подряд умерли на «database is locked» через пять минут, потеряв темп.
    # Журнал с fsync — вот durable-запись; из него карточки доливаются
    # отдельным прогоном (zalit_iz_zhurnala.py), когда база свободна.
    jl.write(json.dumps({k: row.get(k) for k in D.FIELDS if k != "raw"},
                        ensure_ascii=False) + "\n")
    if n % 25 == 0:
        jl.flush()
        os.fsync(jl.fileno())
    time.sleep(0.14)
jl.flush()
os.fsync(jl.fileno())
jl.close()
всего = sum(1 for _ in io.open(ЖУРНАЛ, encoding="utf-8", errors="ignore"))
print(json.dumps({
    "в_очереди_было": len(todo), "получено": ok,
    "нет_в_ЕГРЮЛ": miss, "ошибок": err, "последняя_ошибка": последняя,
    "строк_в_журнале": всего, "секунд": round(time.time() - t0, 1),
    "осталось_по_сделкам": len(todo) - ok - miss}, ensure_ascii=False))
