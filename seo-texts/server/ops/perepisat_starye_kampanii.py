# -*- coding: utf-8 -*-
"""Письма старых кампаний 7-9 переписать с паспортом сайта.

Владелец 20.08: «если ещё не было профиля компании, тогда перепиши с
профилем, либо скипни чтобы ждать пока появится профиль».

49 карточек написаны 12-17 августа, когда паспорт сайта до промпта ещё не
доезжал. Сегодня паспорт есть у 46 из них — их переписываем штатной
перегенерацией (ai_quota.regenerate_review кладёт новый текст в ТУ ЖЕ
строку очереди, вместе с текстом сайта и правилом «называть только то,
что в тексте есть»). Троим без паспорта писать пока не из чего: снимаем
с причиной, вернутся, когда обогащение их доберёт.

Журнал durable на сервере: прогон резюмируемый.

    python zapusk_svoego_skripta.py ops/perepisat_starye_kampanii.py
    python zapusk_svoego_skripta.py ops/perepisat_starye_kampanii.py --катить
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

ЖУРНАЛ = r"C:\sender\_ops\perepisat-starye.jsonl"
КАТИТЬ = "--катить" in sys.argv
_числа = [int(a) for a in sys.argv[1:] if a.isdigit()]
ПОТОЛОК = _числа[0] if _числа else 60
ПОТОКОВ = _числа[1] if len(_числа) > 1 else 8
ПОЛЯ = ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб",
        "мощности")

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

уже = set()
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(s)
            if z.get("ок"):
                уже.add(int(z["id"]))
        except Exception:                                        # noqa: BLE001
            pass

with store._lock:
    ряды = store._conn.execute(
        "SELECT c.id, c.campaign_id, r.inn, r.company_name "
        "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='pending' AND c.campaign_id NOT IN (10,11) "
        "ORDER BY c.id").fetchall()

счёт = Counter()
работа, без_паспорта = [], []
for r in ряды:
    rid = int(r["id"])
    if rid in уже:
        счёт["уже переписано"] += 1
        continue
    try:
        д = q._site_facts(str(r["inn"] or "")) or {}
    except Exception:                                            # noqa: BLE001
        д = {}
    if not any(д.get(k) for k in ПОЛЯ):
        без_паспорта.append((rid, str(r["company_name"] or "")[:40]))
        счёт["паспорта нет — ждём обогащение"] += 1
        continue
    работа.append(rid)
    счёт["переписать с паспортом"] += 1
работа = работа[:ПОТОЛОК]

print(f"карточек старых кампаний: {len(ряды)}")
for к, n in счёт.most_common():
    print(f"  {n:>4}  {к}")
for rid, имя in без_паспорта:
    print(f"    без паспорта: #{rid} {имя}")

if not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить — --катить")
    raise SystemExit(0)

# ---- снять тех, кому писать не из чего --------------------------------- #
снято = 0
for rid, имя in без_паспорта:
    try:
        ок = store.confirm_decide(
            rid, status="skipped",
            reason="ждём паспорт сайта: обогащение ещё не собрало профиль, "
                   "писать не из чего",
            decided_by="разбор старых кампаний 20.08")
        снято += 1 if ок is not False else 0
    except Exception as ex:                                      # noqa: BLE001
        print(f"  #{rid} не снялось: {str(ex)[:90]}")
print(f"снято «ждём паспорт»: {снято}")

# ---- переписать остальных ---------------------------------------------- #
замок = threading.Lock()
итоги = Counter()
начало = time.time()


def в_журнал(зап):
    with замок:
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as ж:
            ж.write(json.dumps(зап, ensure_ascii=False) + "\n")
            ж.flush()
            os.fsync(ж.fileno())


def одно(rid):
    было = store.confirm_get(int(rid)) or {}
    try:
        res = q.regenerate_review(int(rid))
        ок = bool(res.get("ok"))
        метка = ("переписано" if ок
                 else f"отказ: {str(res.get('reason'))[:70]}")
    except Exception as ex:                                      # noqa: BLE001
        ок, метка = False, f"сбой: {type(ex).__name__} {str(ex)[:70]}"
    стало = store.confirm_get(int(rid)) or {}
    в_журнал({"id": rid, "ок": ок, "метка": метка,
              "фирма": str(было.get("company_name") or "")[:60],
              "было_тема": было.get("subject"),
              "стало_тема": стало.get("subject"),
              "стало_тело": стало.get("body")})
    with замок:
        итоги[метка.split(":")[0]] += 1
    print(f"  #{rid} {str(было.get('company_name') or '')[:30]:<30} {метка}")
    return ок


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
    list(pool.map(одно, работа))

print(f"\nитог за {int(time.time() - начало)} с: {dict(итоги)}")
print("журнал:", ЖУРНАЛ)
