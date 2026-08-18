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
  * «сбой рецензии» - модель не ответила, вердикта нет;
  * КОРПОРАТИВНЫЙ почтовый сервер получателя (mx_provider вне
    yandex/mailru/google/outlook). Фильтр стоял на генерации, а на входе в
    автоотправку его не было - 18.08 так уехало 26 писем из 525, и владелец
    поймал это раньше меня: «так у нас же все письма были не на
    корпоративных серверах?». Свой сервер чаще всего отбивает почту с
    молодых доменов по политике, и его отказ бьёт по репутации;
  * адрес с приговором пробы («нет ящика», «нет MX») - такому писать нельзя
    независимо от качества текста.

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

ЧУЖИЕ_ПОЧТОВИКИ = ("yandex", "mailru", "google", "outlook")
счёт = Counter()
к_катанию = []
for rid in годные:
    with store._lock:
        r = store._conn.execute(
            """SELECT c.status, COALESCE(rc.mx_provider,''),
                      COALESCE(p.verdict,'')
                 FROM confirm_reviews c
                 LEFT JOIN recipients rc ON rc.id=c.recipient_id
                 LEFT JOIN addr_probe p ON p.email=lower(c.email)
                WHERE c.id=?""", (rid,)).fetchone()
    if not r:
        счёт["письма нет"] += 1
        continue
    if str(r[0]) != "pending":
        счёт[f"статус {r[0]} - пропускаю"] += 1
        continue
    if str(r[1]).strip().lower() not in ЧУЖИЕ_ПОЧТОВИКИ:
        счёт[f"корпоративный почтовый сервер ({r[1] or 'неизвестен'})"] += 1
        continue
    if str(r[2]) in ("нет ящика", "нет MX"):
        счёт[f"приговор пробы: {r[2]}"] += 1
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
