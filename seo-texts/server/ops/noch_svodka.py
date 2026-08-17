# -*- coding: utf-8 -*-
"""Сколько писем РЕАЛЬНО легло в панель - против того, сколько оплачено.

Владелец 17.08: «обязательно проверяй что письма пошли в панель, потому что
расход вижу у провайдера, писем нет». Это не паранойя, а замеренный случай:
кнопка панели гоняла гейт рода деятельности (две линзы через провайдера на
компанию) и отваливалась по таймауту - деньги списаны, писем ноль.

Поэтому сверяем ТРИ числа на каждом круге ночного прогона:
  * журнал: сколько записей «итог» с ок=1 и на какую сумму;
  * очередь: сколько строк confirm_reviews в кампании 10 создано сегодня;
  * расхождение - если журнал говорит «ок», а строки в очереди нет, письмо
    оплачено и потеряно, и круг надо останавливать, а не продолжать.

    python zapusk_svoego_skripta.py ops/noch_svodka.py
"""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
КАМПАНИЯ = int(sys.argv[1]) if len(sys.argv) > 1 else 10

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

счёт = Counter()
цена = 0.0
review_ids = set()
если_ок_без_очереди = []
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:                                       # noqa: BLE001
            continue
        if z.get("этап") != "итог":
            if z.get("этап") == "сгенерировано":
                счёт["журнал: текст написан"] += 1
                ц = float(z.get("цена_$") or 0)
                цена += ц
                # ДЕНЬГИ, УШЕДШИЕ В НИКУДА. Владелец: «расход вижу у
                # провайдера, писем нет». Вот главный его источник: письмо
                # написано и оплачено, а гейт его забраковал - в панель оно
                # не попадает. Считаем эту цену отдельно, иначе она прячется
                # в общей сумме.
                if z.get("ок"):
                    счёт["_цена_ок_x1000"] += int(ц * 1000)
                else:
                    счёт["_цена_брака_x1000"] += int(ц * 1000)
            continue
        счёт["журнал: итогов"] += 1
        if z.get("ок"):
            счёт["журнал: ок"] += 1
            rid = z.get("review_id")
            if rid:
                review_ids.add(int(rid))
            else:
                если_ок_без_очереди.append(z.get("инн"))
        else:
            счёт["журнал: брак"] += 1
            причина = str((z.get("брак") or [""])[0])[:44]
            счёт[f"  брак: {причина}"] += 1

with store._lock:
    в_очереди = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=?",
        (КАМПАНИЯ,)).fetchone()[0]
    pending = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=? "
        "AND status='pending'", (КАМПАНИЯ,)).fetchone()[0]
    есть = set()
    if review_ids:
        метки = ",".join("?" * len(review_ids))
        есть = {r[0] for r in store._conn.execute(
            f"SELECT id FROM confirm_reviews WHERE id IN ({метки})",
            [int(i) for i in review_ids])}

потеряны = sorted(review_ids - есть)
print(f"кампания {КАМПАНИЯ}: строк в очереди {в_очереди}, из них pending {pending}")
for k, n in счёт.most_common():
    print(f"  {k:<46} {n}")
print(f"  журнал: потрачено ${цена:.2f}")
print(f"\nсверка: журнал назвал review_id {len(review_ids)}, "
      f"в базе нашлось {len(есть)}")
if потеряны:
    print(f"  ПОТЕРЯНЫ (оплачены, в очереди нет): {потеряны[:20]}")
if если_ок_без_очереди:
    print(f"  ок без review_id: {len(если_ок_без_очереди)} "
          f"(докладывает ops/partiya_dolozhit_iz_zhurnala.py)")
if not потеряны and not если_ок_без_очереди:
    print("  всё, за что заплатили, лежит в панели")
