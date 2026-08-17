# -*- coding: utf-8 -*-
"""Кнопка «Сгенерировать в очередь» целиком: от вызова до писем в базе.

Проверять надо не candidates, а весь путь. Владелец спросил прямо: «а кнопку
сгенерировать письма починил?» - и честный ответ до этого замера был «ускорил
отбор, но саму кнопку от начала до конца не проверял».

Кнопка зовёт POST /ai/quota/run -> AiQuota.start_run(campaign_id, count).
Прогон идёт В ФОНЕ, ответ приходит сразу - поэтому «ошибки нет» ещё не
значит «письма будут». Меряем так: считаем строки очереди ДО, зовём
start_run, ждём и считаем ПОСЛЕ.

ВАЖНО ПРО ВЫБОР КАМПАНИИ. Фронт зовёт кнопку с `current?.campaign_id ?? 1` -
кампанией ОТКРЫТОГО ПИСЬМА, а не выбранной группы. Оператор, у которого
открыто письмо кампании 7, нажимает кнопку и генерирует в кампанию 7, хотя в
выпадашке стоит «Партия 935». Поэтому кампанию берём аргументом и печатаем,
из какого сегмента она набирает.

    python zapusk_svoego_skripta.py ops/knopka_e2e.py 10 3 300
"""
import sys
import time

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                      # noqa: E402
from sender.config import Config                                # noqa: E402
from sender.store import Store                                  # noqa: E402

КАМПАНИЯ = int(sys.argv[1]) if len(sys.argv) > 1 else 10
СКОЛЬКО = int(sys.argv[2]) if len(sys.argv) > 2 else 3
ЖДАТЬ = int(sys.argv[3]) if len(sys.argv) > 3 else 300

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)


def сколько(cid):
    with store._lock:
        return store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=?",
            (cid,)).fetchone()[0]


camp = store.get_campaign(КАМПАНИЯ)
print(f"кампания {КАМПАНИЯ}: {getattr(camp, 'name', None)!r}, "
      f"сегмент отбора {q._segment(КАМПАНИЯ)!r}")
было = сколько(КАМПАНИЯ)
print(f"строк в очереди ДО: {было}")

т0 = time.time()
try:
    состояние = q.start_run(КАМПАНИЯ, actor="ops:knopka_e2e", count=СКОЛЬКО)
except Exception as ex:                                         # noqa: BLE001
    print(f"start_run УПАЛ через {time.time() - т0:.1f}с: "
          f"{type(ex).__name__} {str(ex)[:200]}")
    raise SystemExit(1)
print(f"start_run ответил за {time.time() - т0:.1f}с: {состояние}")

# Прогон фоновый - ждём появления строк, а не окончания вызова.
предел = time.time() + ЖДАТЬ
стало = было
while time.time() < предел:
    time.sleep(15)
    стало = сколько(КАМПАНИЯ)
    print(f"  {int(time.time() - т0):>4}с: строк {стало} "
          f"(+{стало - было})")
    if стало - было >= СКОЛЬКО:
        break

print(f"\nитог: было {было}, стало {стало}, прибавилось {стало - было} "
      f"из заказанных {СКОЛЬКО} за {int(time.time() - т0)}с")
if стало > было:
    with store._lock:
        for r in store._conn.execute(
                "SELECT id, status, email, subject FROM confirm_reviews "
                "WHERE campaign_id=? ORDER BY id DESC LIMIT ?",
                (КАМПАНИЯ, стало - было)):
            print(f"  #{r[0]} {r[1]} {str(r[2])[:34]:<36} {str(r[3])[:52]}")
else:
    print("  ПИСЕМ НЕ ПРИБАВИЛОСЬ - кнопка не работает end-to-end")
