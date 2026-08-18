# -*- coding: utf-8 -*-
"""Снять из очереди письма, которые не спасла и перегенерация.

Владелец 18.08: «снимай». Речь о письмах, которые прошли полный круг:
рецензент по сайту сказал «не годно» -> письмо перегенерировали с текстом
сайта в промпте -> рецензент перечитал и снова сказал «не годно». Там не
текст плохой, а адресат не тот: сайт не подтверждает ни компрессорной, ни
сортировочной темы. Переписывать в третий раз - жечь деньги.

Снимаем ТОЛЬКО тех, кого уже пытались чинить: письмо с «не годно» без
попытки перегенерации - это не безнадёга, а недоделанная работа.

«нечем проверить» НЕ трогаем: это не приговор письму, а признание, что
сайт не открылся.

Статус ставим через confirm_decide(status='skipped') - он одной
транзакцией гасит и решение, и письмо в messages. Список снятого пишем в
durable-журнал на сервере: снятое надо уметь перечислить и вернуть.

Без аргумента - сухой прогон.

    python zapusk_svoego_skripta.py ops/snyat_neispravimyy_brak.py
    python zapusk_svoego_skripta.py ops/snyat_neispravimyy_brak.py --катить
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

РЕЦЕНЗИИ = r"C:\sender\_ops\rezenzii-pisem.jsonl"
ПЕРЕГЕН = r"C:\sender\_ops\peregeneraciya-braka.jsonl"
ЖУРНАЛ = r"C:\sender\_ops\snyatyy-brak.jsonl"
КАТИТЬ = "--катить" in sys.argv

верд = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = z
    except Exception:                                            # noqa: BLE001
        pass

пытались = set()
if os.path.exists(ПЕРЕГЕН):
    for s in io.open(ПЕРЕГЕН, encoding="utf-8", errors="replace"):
        try:
            пытались.add(int(json.loads(s)["id"]))
        except Exception:                                        # noqa: BLE001
            pass

брак = sorted(i for i, v in верд.items()
              if str(v.get("verdict") or "") == "не годно")
безнадёга = [i for i in брак if i in пытались]
print(f"«не годно» сейчас: {len(брак)}; из них уже перегенерировали: "
      f"{len(безнадёга)}, ещё не пытались: {len(брак) - len(безнадёга)}")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

счёт = Counter()
к_снятию = []
for rid in безнадёга:
    with store._lock:
        r = store._conn.execute(
            "SELECT status FROM confirm_reviews WHERE id=?", (rid,)).fetchone()
    if not r:
        счёт["письма нет"] += 1
        continue
    if str(r[0]) != "pending":
        счёт[f"статус {r[0]} - не трогаю"] += 1
        continue
    к_снятию.append(rid)
print(f"к снятию: {len(к_снятию)}")
for k, n in счёт.most_common():
    print(f"  {k}: {n}")

if not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить - аргумент --катить")
    raise SystemExit(0)

снято = сбоев = 0
for rid in к_снятию:
    z = верд.get(rid) or {}
    претензия = "; ".join(str(x) for x in (z.get("pretenzii") or []))[:300]
    try:
        ок = store.confirm_decide(
            rid, status="skipped",
            reason="сайт не подтверждает письмо и после перегенерации: "
                   + (претензия or "рецензент: не годно"),
            decided_by="рецензент по сайту + перегенерация (18.08)")
        if ок is False:
            сбоев += 1
            continue
        снято += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": rid, "фирма": z.get("фирма"),
                                "url": z.get("url"),
                                "претензии": z.get("pretenzii")},
                               ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex:                                      # noqa: BLE001
        сбоев += 1
        if сбоев <= 5:
            print(f"  #{rid}: {type(ex).__name__} {str(ex)[:110]}")

print(f"\nснято: {снято} | сбоев: {сбоев}")
with store._lock:
    ост = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=10 "
        "AND status='pending'").fetchone()[0]
print(f"осталось pending в кампании 10: {ост}")
