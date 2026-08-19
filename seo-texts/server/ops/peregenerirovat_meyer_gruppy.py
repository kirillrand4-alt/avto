# -*- coding: utf-8 -*-
"""Перегенерировать письма групп «мейер-рентген» и «мейер-фото».

Владелец 19.08: «мейер рентген и мейер фото перепиши по актуальным
правилам». Правила Meyer сегодня расширены пулами Мартюшова: обороты
перехода к теме и четыре формы просьбы перенаправить вместо одной. Письма,
лежащие в очереди, написаны по старым - их надо переписать.

Перегенерация штатная (ai_quota.regenerate_review): новый текст ложится в
ТУ ЖЕ строку очереди, оператор увидит обновлённое письмо на том же месте.
Берём только pending: отправленное переписывать поздно.

Журнал durable, прогон резюмируемый.

    python zapusk_svoego_skripta.py ops/peregenerirovat_meyer_gruppy.py
    python zapusk_svoego_skripta.py ops/peregenerirovat_meyer_gruppy.py 40 --катить
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

ГРУППЫ = ("мейер-рентген", "мейер-фото")
ЖУРНАЛ = r"C:\sender\_ops\peregeneraciya-meyer.jsonl"
КАТИТЬ = "--катить" in sys.argv
_числа = [int(a) for a in sys.argv[1:] if a.isdigit()]
ПОТОЛОК = _числа[0] if _числа else 200
ПОТОКОВ = _числа[1] if len(_числа) > 1 else 6

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

группы = store.recipient_groups().get("по_id") or {}
нужные = {rid for rid, гр in группы.items() if any(g in гр for g in ГРУППЫ)}
print(f"получателей в группах {ГРУППЫ}: {len(нужные)}")

with store._lock:
    ряды = store._conn.execute(
        "SELECT id, recipient_id, status, COALESCE(campaign_id,0) "
        "FROM confirm_reviews WHERE status='pending'").fetchall()
счёт = Counter()
работа = []
for rid, rcid, st, camp in ряды:
    if rcid is None or int(rcid) not in нужные:
        continue
    if int(rid) in уже:
        счёт["уже переписано"] += 1
        continue
    счёт[f"кампания {camp}"] += 1
    работа.append(int(rid))
работа = работа[:ПОТОЛОК]
print(f"к перезаписи: {len(работа)}")
for k, n in счёт.most_common():
    print(f"  {k}: {n}")
if not работа or not КАТИТЬ:
    print("\nсухой прогон: ничего не тронуто. Катить — аргумент --катить"
          if работа else "переписывать нечего")
    raise SystemExit(0)

начало = time.time()
итоги = Counter()
замок = threading.Lock()


def одно(rid):
    было = store.confirm_get(int(rid)) or {}
    try:
        res = q.regenerate_review(int(rid))
        ок = bool(res.get("ok"))
        метка = ("переписано" if ок
                 else f"отказ: {str(res.get('reason'))[:60]}")
    except Exception as ex:                                      # noqa: BLE001
        ок, res = False, {"reason": f"{type(ex).__name__}: {str(ex)[:120]}"}
        метка = f"сбой: {type(ex).__name__}"
    строка = json.dumps({
        "id": rid, "ок": ок, "почему": res.get("reason"),
        "fails": res.get("fails"),
        "фирма": было.get("company_name") or было.get("inn"),
        "тема_до": было.get("subject"),
        "тело_до": (было.get("body") or "")[:3000]}, ensure_ascii=False)
    with замок:
        итоги[метка] += 1
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(строка + "\n")
            f.flush()
            os.fsync(f.fileno())
        n = sum(итоги.values())
        if n % 10 == 0:
            print(f"  {n}/{len(работа)} за {time.time() - начало:.0f}с: "
                  f"{dict(итоги)}", flush=True)


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as ex_:
    list(ex_.map(одно, работа))
print(f"\nготово за {time.time() - начало:.0f}с")
for k, n in итоги.most_common():
    print(f"  {n:>4}  {k}")
