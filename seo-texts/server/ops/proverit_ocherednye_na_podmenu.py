# -*- coding: utf-8 -*-
"""Не приклеен ли к карточке чужой сайт: проверка всей очереди дешёвой моделью.

Повод. Письмо #1010 адресовано ООО «Старт», ОКВЭД 10.61 — мукомольное и
крупяное производство. А почта info@business-gazeta.ru, и паспорт с
текстом сайта сняты с казанского издания «Бизнес Online». Письмо про
очистку крупы уехало бы в редакцию газеты.

Механически это ловится тем же дешёвым предклассификатором: он судит по
ПАСПОРТУ, то есть по тому, что реально написано на приклеенном сайте.
Если паспорт говорит «газета», а письмо ушло по компрессорной или
мейеровской кампании — паспорт не от той компании либо компания не наша.
Стоит $0.0003 на компанию.

Берём то, что ещё можно остановить: одобренные со слотом и очередь
подтверждения. Ничего не меняем — только показываем.
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

sys.path.insert(0, r"C:\sender\_ops")
МОДЕЛЬ = os.environ.get("PRECLASS_MODEL", "gpt-5.4-mini")
ЖУРНАЛ = r"C:\sender\_ops\podmena-saytov.jsonl"
ШАГ = 20
ПОТОКОВ = 6

СИСТЕМА = """Ты классификатор промышленных компаний. По описанию с сайта
реши, какое из двух направлений может ей что-то продать.

КЦ - компрессорное оборудование: компрессоры, осушители, генераторы азота и
кислорода, пневмоинструмент. Подходит почти любому, где есть цех, стройка,
монтаж, ремонт, техника: металлообработка, металлоконструкции, дороги,
кабель, лифты, машиностроение, деревообработка, покраска, автосервис, ЖКХ,
вывоз отходов.

МЕЙЕР - два станка, и подходить может ЛЮБОЙ ИЗ ДВУХ:
* ФОТОСЕПАРАТОР - только СЫПУЧИЙ поток: зерно, крупы, мука, семена, орехи,
  сухофрукты, ягоды, бобовые, овощи на переработку, комбикорм, кофе, чай,
  специи, замороженные ягоды и овощи;
* РЕНТГЕН-ИНСПЕКЦИЯ упакованного продукта - шире: мясо и рыба, колбасы,
  полуфабрикаты, кондитерка, хлеб, молочка, консервы, готовая еда.
Напитки и розлив воды НЕ подходят.

НИКАКОЕ - когда сайт показывает не производство и не работы: СМИ и
редакция, интернет-магазин без своего выпуска, торговая площадка,
консалтинг, клиника, банк, турагентство, госорган.

ОТВЕТ - СТРОГО JSON без текста вокруг:
{"firmy":[{"inn":"...","napravlenie":"кц|мейер|оба|никакое"}]}"""

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

with store._lock:
    ряды = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.email, c.status cst, m.status mst, "
        "       r.inn, r.company_name "
        "FROM confirm_reviews c "
        "LEFT JOIN messages m ON m.id = c.message_id "
        "LEFT JOIN recipients r ON r.id = c.recipient_id "
        "WHERE (c.status='pending') "
        "   OR (c.status IN ('approved','edited') "
        "       AND m.status IN ('scheduled','sending'))").fetchall()

# Паспорт одной строкой — то же, что видит генерация.
ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб")
работа = []
без_паспорта = 0
for r in ряды:
    инн = str(r["inn"] or "").strip()
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
    п = "\n".join(куски)[:900]
    if not п:
        без_паспорта += 1
        continue
    работа.append((int(r["id"]), инн, str(r["company_name"] or "")[:40],
                   int(r["campaign_id"]), п))

print(f"писем к проверке: {len(ряды)} | с паспортом: {len(работа)} | "
      f"без паспорта: {без_паспорта}")

# Кампания -> ожидаемое направление.
НАПР = {7: "мейер", 8: "мейер", 9: "кц", 10: "кц", 11: "мейер"}


def пачка(куски):
    блоки = [f"ИНН {и} · {имя}\n{п}" for _r, и, имя, _k, п in куски]
    try:
        m = gen_provider._raw_stream(
            [{"role": "user", "content": "Компании:\n\n" + "\n\n".join(блоки)}],
            МОДЕЛЬ, 2000, thinking=False, system=СИСТЕМА)
        т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        мм = re.search(r"\{.*\}", т, re.S)
        д = json.loads(мм.group(0)) if мм else {}
    except Exception as ex:                                      # noqa: BLE001
        print(f"  пачка не прошла: {str(ex)[:90]}")
        return []
    по_инн = {}
    for v in (д.get("firmy") or []):
        и = "".join(c for c in str(v.get("inn") or "") if c.isdigit())
        по_инн[и] = str(v.get("napravlenie") or "").strip().lower()
    из_ = []
    for rid, и, имя, k, _п in куски:
        н = по_инн.get(и, "")
        ждали = НАПР.get(k, "кц")
        плохо = н and n_плохо(н, ждали)
        из_.append({"id": rid, "inn": и, "имя": имя, "кампания": k,
                    "дешёвый": н, "ждали": ждали, "мимо": bool(плохо)})
    return из_


def n_плохо(н, ждали):
    if н == "никакое":
        return True
    if н == "оба":
        return False
    return н != ждали


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
print("вердикты:", dict(Counter(z["дешёвый"] or "—" for z in итог)))
мимо = [z for z in итог if z["мимо"]]
print(f"\nМИМО НАПРАВЛЕНИЯ: {len(мимо)}")
for z in мимо[:60]:
    print(f"  #{z['id']} к{z['кампания']} {z['имя']:<40} "
          f"дешёвый={z['дешёвый']} ждали={z['ждали']}")
