# -*- coding: utf-8 -*-
"""Перегенерировать письма, забракованные рецензентом по сайту.

413 писем партии 935 получили «не годно»: письмо называет процесс, участок
или линию, которых на сайте компании нет. Причина не в нехватке данных -
паспорт сайта до промпта доезжал, и заполнен он у годных и бракованных
одинаково. Дело в том, что модели было НЕЧЕМ СЕБЯ ПРОВЕРИТЬ: списки
паспорта лоссовые, а живого текста сайта в промпте не было.

Теперь текст сайта лежит в промпте (enrich.db/site_text, собирает
ops/sobrat_teksty_saytov.py) вместе с жёстким правилом: процессы и линии
называть только те, что есть в тексте или в паспорте. Перегенерация -
штатная (ai_quota.regenerate_review): новый текст ложится в ТУ ЖЕ строку
очереди.

Берём ТОЛЬКО pending: отправленное переписывать поздно.

Журнал durable на сервере: каждое письмо записывается сразу, прогон
резюмируемый.

    python zapusk_svoego_skripta.py ops/peregenerirovat_brak.py            # сколько их
    python zapusk_svoego_skripta.py ops/peregenerirovat_brak.py 50 --катить
"""
import io
import json
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ЖУРНАЛ = r"C:\sender\_ops\peregeneraciya-braka.jsonl"
КАТИТЬ = "--катить" in sys.argv
_числа = [int(a) for a in sys.argv[1:] if a.isdigit()]
ПОТОЛОК = _числа[0] if _числа else 500
# Перегенерация одного письма - это полный круг генерации с механическим QA
# и ретраями, секунды на письмо. Последовательно 400 писем это часы, поэтому
# идём потоками: каждый вызов regenerate_review собирает свой генератор сам,
# общая у них только база (у стора свой замок).
ПОТОКОВ = _числа[1] if len(_числа) > 1 else 8

последний = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        последний[int(z["id"])] = str(z.get("verdict") or "")
    except Exception:                                            # noqa: BLE001
        continue
брак = sorted(i for i, в in последний.items() if в == "не годно")

уже = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
            if z.get("ок"):
                уже.add(int(z["id"]))
        except Exception:                                        # noqa: BLE001
            pass

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

работа = []
счёт = Counter()
for rid in брак:
    if rid in уже:
        счёт["уже перегенерировано"] += 1
        continue
    row = store.confirm_get(int(rid))
    if not row:
        счёт["письма нет"] += 1
        continue
    if row.get("status") != "pending":
        счёт[f"статус {row.get('status')} — не трогаю"] += 1
        continue
    работа.append(rid)
работа = работа[:ПОТОЛОК]

print(f"забраковано рецензентом: {len(брак)}")
for к, n in счёт.most_common():
    print(f"  {к}: {n}")
print(f"к перегенерации сейчас: {len(работа)}")

# Текст сайта есть не у всех — говорим об этом заранее, а не после прогона.
try:
    import sqlite3
    con = sqlite3.connect(r"file:C:\sender\enrich.db?mode=ro", uri=True,
                          timeout=10)
    с_текстом = 0
    for rid in работа:
        row = store.confirm_get(int(rid))
        r = con.execute("SELECT chars FROM site_text WHERE inn=?",
                        (str(row.get("inn") or "").strip(),)).fetchone()
        if r and int(r[0] or 0) > 200:
            с_текстом += 1
    con.close()
    print(f"из них с собранным текстом сайта: {с_текстом}")
except Exception as ex:                                          # noqa: BLE001
    print("текст сайта не проверить:", str(ex)[:120])

if not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить — аргумент --катить")
    raise SystemExit(0)

начало = time.time()
итоги = Counter()
замок = threading.Lock()
сделано = [0]


def одно(rid):
    # Старый текст сохраняем ДО перегенерации: regenerate_review пишет в ту
    # же строку, и сравнить «было/стало» потом будет не с чем. Письмо
    # забраковано, но глазами смотреть надо оба.
    было = store.confirm_get(int(rid)) or {}
    try:
        res = q.regenerate_review(int(rid))
        ок = bool(res.get("ok"))
        метка = ("перегенерировано" if ок
                 else f"отказ: {str(res.get('reason'))[:60]}")
    except Exception as ex:                                      # noqa: BLE001
        ок, res = False, {"reason": f"{type(ex).__name__}: {str(ex)[:120]}"}
        метка = f"сбой: {type(ex).__name__}"
    строка = json.dumps({
        "id": rid, "ок": ок, "почему": res.get("reason"),
        "фирма": было.get("company_name") or было.get("inn"),
        "тема_до": было.get("subject"),
        "тело_до": (было.get("body") or "")[:4000]}, ensure_ascii=False)
    with замок:
        итоги[метка] += 1
        сделано[0] += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(строка + "\n")
            f.flush()
            os.fsync(f.fileno())
        if сделано[0] % 25 == 0:
            print(f"  {сделано[0]}/{len(работа)} за "
                  f"{time.time() - начало:.0f}с: {dict(итоги)}", flush=True)


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as ex_:
    list(ex_.map(одно, работа))

print(f"\nготово за {time.time() - начало:.0f}с")
for к, n in итоги.most_common():
    print(f"  {n:>4}  {к}")
print("\nдальше: рецензент с --перечитать-брак, потом годные в автоотправку")
