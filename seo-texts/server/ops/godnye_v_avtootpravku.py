# -*- coding: utf-8 -*-
"""В автоотправку - письма с вердиктом «годно» от рецензента по сайту.

Владелец: «если будут читать агенты и отправлять - будет быстрее? хотелось
бы за полчаса перевести 500 писем в автоотправку». Читает рецензент
(ops/rezenzent_pisem.py): письмо плюс текст сайта компании, вопрос один -
какие утверждения письма сайт не подтверждает.

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ prochitannye_v_avtootpravku.py: там список именной, я
читал каждое письмо сам. Здесь читал рецензент, а я проверил его выборкой.

ЧТО ПОКАЗАЛА ВЫБОРКА (мои глаза против его вердикта):
  * «годно» - 4 из 4 совпало (#1851 ДКС, #2052 Энергопромавтоматика,
    #2308 Лотос, плюс пересуд #2331/#2335/#2336). Утверждения отраслевые и
    с оговорками, выдумок нет;
  * «не годно» - 1 придирка из 2. Справедливо #2343 («весь спектр операций
    от катаракты до витреоретинальных», а витреоретинальных на сайте нет);
    придирка #1936 «Дортранссервис» - рецензент отверг «производство
    асфальтобетона и битумных составов», хотя сайт сам перечисляет установки
    битумной эмульсии и ПБВ.
Отсюда правило прогона: катим ТОЛЬКО «годно». «Не годно» не выбрасываем -
там есть годные, их надо пересудить отдельно.

НЕ КАТИМ вовсе:
  * «нечем проверить» - сайт не открылся, сверять утверждения нечем;
  * «сбой рецензии» - модель не ответила, вердикта нет.

Без аргумента - сухой прогон.

    python zapusk_svoego_skripta.py ops/godnye_v_avtootpravku.py
    python zapusk_svoego_skripta.py ops/godnye_v_avtootpravku.py --катить
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
ЖУРНАЛ = r"C:\sender\_ops\godnye-v-avtootpravku.jsonl"
КАТИТЬ = "--катить" in sys.argv
ПОТОЛОК = int(next((a for a in sys.argv[1:] if a.isdigit()), "10000"))

верд = {}
for s in io.open(РЕЦЕНЗИИ, encoding="utf-8"):
    try:
        z = json.loads(s)
        верд[int(z["id"])] = z
    except Exception:                                           # noqa: BLE001
        pass
годные = sorted(i for i, v in верд.items() if v.get("verdict") == "годно")
print(f"вердиктов всего {len(верд)}, из них «годно» {len(годные)}")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

счёт = Counter()
к_катанию = []
for rid in годные:
    with store._lock:
        r = store._conn.execute(
            "SELECT status FROM confirm_reviews WHERE id=?", (rid,)).fetchone()
    if not r:
        счёт["письма нет"] += 1
        continue
    if str(r[0]) != "pending":
        счёт[f"статус {r[0]} - пропускаю"] += 1
        continue
    к_катанию.append(rid)
к_катанию = к_катанию[:ПОТОЛОК]
print(f"к переводу в автоотправку: {len(к_катанию)}")
for k, n in счёт.most_common():
    print(f"  {k}: {n}")

if not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить - аргумент --катить")
    raise SystemExit(0)

переведено = сбоев = 0
for rid in к_катанию:
    try:
        ок = store.confirm_decide(
            rid, status="approved",
            decided_by="рецензент по сайту (18.08), выборка проверена глазами")
        if ок is False:
            сбоев += 1
            continue
        переведено += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": rid, "фирма": верд[rid].get("фирма"),
                                "url": верд[rid].get("url")},
                               ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex:                                     # noqa: BLE001
        сбоев += 1
        if сбоев <= 5:
            print(f"  #{rid}: {type(ex).__name__} {str(ex)[:110]}")

print(f"\nпереведено в автоотправку: {переведено} | сбоев: {сбоев}")
with store._lock:
    одобр = store._conn.execute(
        "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=10 "
        "AND status='approved'").fetchone()[0]
print(f"всего approved в кампании 10: {одобр}")
