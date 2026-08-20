# -*- coding: utf-8 -*-
"""Про ту ли компанию паспорт: сверка ОКВЭД карточки с фактами сайта.

Два подтверждённых случая подмены. #1010: ОКВЭД 10.61 «мукомольное и
крупяное», а паспорт — казанское издание «Бизнес Online». #3154: ОКВЭД
10.83 «производство чая и кофе», а паспорт — племзавод с роботизированной
молочной фермой на 360 голов. Письмо в обоих случаях построено на чужих
фактах.

Механически имя компании с сайтом не сверить: сайт живёт под брендом, а
не под названием юрлица, и «ЧИСТАВОДА» против «Чистая вода» уже мимо.
Поэтому спрашиваем дешёвую модель об одном: вяжется ли род занятий из
паспорта с ОКВЭДом карточки. Расхождение рода занятий — это подмена;
расхождение в деталях — нет.

Модель на клодовской двери: OpenAI-дверь шлюза сегодня отдаёт 502 и
молчащие стримы.
"""
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, r"C:\sender")
import gen_provider                                              # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

# Хайку на этой задаче не годится: из первых 12 она назвала подменой пять
# карточек, где ОКВЭД просто формальный («обработка металла» в реестре,
# пластик на сайте) — ровно то, что промпт велит подменой НЕ считать.
# Судить берём опус, но по короткому списку кандидатов, а не по всей
# очереди: список даёт бесплатный отбор по имени (chey_sayt_prikleen.py).
МОДЕЛЬ = os.environ.get("SVERKA_MODEL", "claude-opus-4-8")
ТОЛЬКО = {int(a) for a in sys.argv[1:] if a.isdigit()}
ЖУРНАЛ = r"C:\sender\_ops\sverka-pasporta.jsonl"
ШАГ = 12
ПОТОКОВ = 6

СИСТЕМА = """Тебе дают карточку компании из реестра (название и ОКВЭД) и
выжимку с сайта, который к ней привязан. Ответь на ОДИН вопрос: это одна
и та же компания или к карточке привязан сайт ЧУЖОЙ компании.

ПОДМЕНА - когда род занятий разный по СУЩЕСТВУ: в карточке мукомольное
производство, на сайте новостное издание; в карточке чай и кофе, на сайте
молочная ферма; в карточке металлообработка, на сайте турагентство.

НЕ ПОДМЕНА:
* сайт под брендом, а не под названием юрлица;
* ОКВЭД формальный и шире или уже реального дела (обычное дело в России):
  «торговля» в карточке при своём производстве на сайте - НЕ подмена;
* холдинг: сайт группы, а карточка - её юрлицо;
* выжимка бедная, судить не по чему - тогда verdict = "неясно".

ОТВЕТ - СТРОГО JSON без текста вокруг:
{"firmy":[{"inn":"...","verdict":"своя|подмена|неясно","chem":"одной фразой,
что на сайте, если подмена"}]}"""

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

with store._lock:
    ряды = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.email, r.inn, r.company_name, "
        "       COALESCE(r.okved,'') okved "
        "FROM confirm_reviews c "
        "LEFT JOIN messages m ON m.id = c.message_id "
        "LEFT JOIN recipients r ON r.id = c.recipient_id "
        "WHERE (c.status='pending') "
        "   OR (c.status IN ('approved','edited') "
        "       AND m.status IN ('scheduled','sending'))").fetchall()

ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "мощности")
работа = []
for r in ряды:
    инн = str(r["inn"] or "").strip()
    if not инн:
        continue
    try:
        д = q._site_facts(инн) or {}
    except Exception:                                            # noqa: BLE001
        д = {}
    куски = []
    for k in ПОЛЯ:
        v = д.get(k)
        if v:
            куски.append(f"{k}: " + (v if isinstance(v, str)
                                     else "; ".join(map(str, v))[:200]))
    п = "\n".join(куски)[:700]
    if not п:
        continue
    if ТОЛЬКО and int(r["id"]) not in ТОЛЬКО:
        continue
    работа.append({"id": int(r["id"]), "inn": инн,
                   "имя": str(r["company_name"] or "")[:60],
                   "оквэд": str(r["okved"] or "")[:80],
                   "камп": int(r["campaign_id"]), "паспорт": п})

print(f"писем в работе: {len(ряды)} | с паспортом: {len(работа)}")


def пачка(куски):
    блоки = [f"ИНН {г['inn']}\nКАРТОЧКА: {г['имя']} · ОКВЭД {г['оквэд']}\n"
             f"САЙТ: {г['паспорт']}" for г in куски]
    try:
        m = gen_provider._raw_stream(
            [{"role": "user", "content": "\n\n".join(блоки)}],
            МОДЕЛЬ, 1500, thinking=False, system=СИСТЕМА)
        т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        мм = re.search(r"\{.*\}", т, re.S)
        д = json.loads(мм.group(0)) if мм else {}
    except Exception as ex:                                      # noqa: BLE001
        print(f"  пачка не прошла: {str(ex)[:80]}")
        return []
    по = {}
    for v in (д.get("firmy") or []):
        и = "".join(c for c in str(v.get("inn") or "") if c.isdigit())
        по[и] = v
    из_ = []
    for г in куски:
        v = по.get(г["inn"]) or {}
        из_.append(dict(г, verdict=str(v.get("verdict") or "нет ответа"),
                        chem=str(v.get("chem") or "")[:140]))
        из_[-1].pop("паспорт", None)
    return из_


куски = [работа[i:i + ШАГ] for i in range(0, len(работа), ШАГ)]
СТАРТ = time.time()
итог = []
with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
    for из_ in pool.map(пачка, куски):
        итог.extend(из_)
        with open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
            for z in из_:
                ж.write(json.dumps(z, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())

print(f"проверено {len(итог)} за {int(time.time() - СТАРТ)} с")
print("вердикты:", dict(Counter(z["verdict"] for z in итог)))
подмены = [z for z in итог if z["verdict"] == "подмена"]
print(f"\nПОДМЕНА САЙТА: {len(подмены)}")
for z in подмены[:60]:
    print(f"  #{z['id']} к{z['камп']} {z['имя'][:34]:<34} "
          f"ОКВЭД {z['оквэд'][:28]:<28} сайт: {z['chem']}")
