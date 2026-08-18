# -*- coding: utf-8 -*-
"""Снять из очереди письма медицинским учреждениям.

Владелец 18.08, увидев в списке офтальмологическую клинику: «зачем нам
такая компания то?.. вряд ли промышленные генераторы азота, компрессоры,
кислород или что-то под Meyer им нужно». Это решение по адресату, и оно
его.

Рецензент их пропускал, и правильно по своему критерию: он судит, не
противоречит ли письмо сайту, а не нужен ли компании компрессор. Клинике
можно написать письмо, сайту не противоречащее - оно и выходило «годно».
Отбор адресата - отдельный вопрос, и решается он не рецензентом.

РЕЖЕМ: ОКВЭД 86-88 (здравоохранение, соцуслуги) либо медицинское слово в
названии.
НЕ РЕЖЕМ по названию, если ОКВЭД производственный (10-33): фармзавод и
завод медизделий - это цех со сжатым воздухом, а слово «мед» в названии у
них тоже есть. Уже отправленные письма не трогаем - их не вернуть.

Список снятого durable, чтобы вернуть можно было поимённо.

    python zapusk_svoego_skripta.py ops/snyat_medicinu_iz_ocheredi.py
    python zapusk_svoego_skripta.py ops/snyat_medicinu_iz_ocheredi.py --катить
"""
import io
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

ЖУРНАЛ = r"C:\sender\_ops\snyataya-medicina.jsonl"
КАТИТЬ = "--катить" in sys.argv
СЛОВА = ("клиник", "медцентр", "медицинск", "стоматолог", "офтальм",
         "хирург", "диагностик", "поликлиник", "больниц", "госпитал",
         "лечебн", "санатор", "医")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, c.status, COALESCE(rc.okved,''),
                  COALESCE(rc.company_name,''), COALESCE(m.status,'')
             FROM confirm_reviews c
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
             LEFT JOIN messages m ON m.id=c.message_id
            WHERE c.campaign_id IN (10,11)
              AND c.status IN ('pending','approved')""").fetchall()

к_снятию, счёт = [], Counter()
for rid, st, ок, имя, mst in ряды:
    код = re.sub(r"[^0-9.]", "", str(ок))
    класс = код[:2]
    имя_л = str(имя).lower()
    по_названию = any(с in имя_л for с in СЛОВА)
    производство = класс.isdigit() and 10 <= int(класс) <= 33
    if класс in ("86", "87", "88"):
        причина = f"ОКВЭД {код}"
    elif по_названию and not производство:
        причина = "медицинское название"
    elif по_названию and производство:
        счёт[f"название медицинское, но ОКВЭД производственный {класс}"] += 1
        continue
    else:
        continue
    if mst == "sent":
        счёт["уже отправлено - не трогаю"] += 1
        continue
    к_снятию.append((rid, имя, причина, st, mst))

print(f"к снятию: {len(к_снятию)}")
for k, n in счёт.most_common():
    print(f"  {k}: {n}")
print("\nпервые 20:")
for rid, имя, п, st, mst in к_снятию[:20]:
    print(f"  #{rid:<6} {имя[:44]:<46} {st}/{mst or '-'}  {п}")

if not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить - аргумент --катить")
    raise SystemExit(0)

снято = сбоев = 0
for rid, имя, п, _st, _mst in к_снятию:
    try:
        # УЖЕ ОДОБРЕННОЕ РЕШЕНИЕ НЕ ПЕРЕРЕШИВАЕТСЯ. confirm_decide держит
        # аудит-след: строку со статусом approved он назад не отыгрывает и
        # честно отвечает False. Первый прогон так и упёрся - 16 снято, 80
        # отказов. Поэтому у одобренных гасим САМО ПИСЬМО (messages ->
        # skipped): автоотправка берёт только 'scheduled', и письмо из неё
        # выпадает, а след решения остаётся нетронутым.
        ок_ = store.confirm_decide(
            rid, status="skipped",
            reason=f"не наш адресат: медицина ({п})",
            decided_by="решение владельца 18.08")
        if ок_ is False:
            карточка = store.confirm_get(rid) or {}
            mid = карточка.get("message_id")
            if not mid:
                сбоев += 1
                continue
            store.mark_skipped(int(mid),
                               f"снято: не наш адресат, медицина ({п})")
        снято += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": rid, "фирма": имя, "почему": п},
                               ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception as ex:                                      # noqa: BLE001
        сбоев += 1
        if сбоев <= 5:
            print(f"  #{rid}: {type(ex).__name__} {str(ex)[:110]}")
print(f"\nснято: {снято} | сбоев: {сбоев}")
