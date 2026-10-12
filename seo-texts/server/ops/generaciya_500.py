# -*- coding: utf-8 -*-
"""Генерация 500 писем партии «Россия 9000» — фоновый работник.

Владелец 12.10: «500 писем из разных групп (молоко/дерево/руды и тд)».
Список — _ops/partiya-500.json (отобран podgotovit_500: 15 отраслей,
паспорт 5–8 разделов из 8). По одному письму на компанию.

Модели — как в панели (owner: «как есть оставь»): письмо opus-4-8,
проверки sonnet-4-6, best_of из конфига. Подпись модели ложится в каждое
письмо (model_pisma). Письма идут ТОЛЬКО в очередь подтверждения: ничего
не отправляется.

Прогресс — в _ops/gen500-progress.json с fsync: переживает рестарт, а
сами письма durable в confirm_reviews.

Запуск (через zapusk_500.py, отсоединённым процессом):
    python generaciya_500.py <campaign_id>
"""
import io
import json
import os
import sys
import time
import traceback

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

КАМП = int(sys.argv[1])
СПИСОК = sys.argv[2] if len(sys.argv) > 2 else r"C:\sender\_ops\partiya-500.json"
ПРОГРЕСС = r"C:\sender\_ops\gen500-progress.json"


def отметить(**д):
    д["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with io.open(ПРОГРЕСС, "w", encoding="utf-8") as ф:
        json.dump(д, ф, ensure_ascii=False)
        ф.flush()
        os.fsync(ф.fileno())


try:
    cfg = Config.load(r"C:\sender\sender.yaml")
    store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
    q = build_ai_quota(store, cfg)
    ид = json.load(io.open(СПИСОК, encoding="utf-8"))
    свои, видели = [], set()
    for rid in ид:
        r = store.get_recipient(int(rid))
        if r is None:
            continue
        инн = str(getattr(r, "inn", "") or "")
        if инн and инн in видели:
            continue                     # одно письмо на компанию
        видели.add(инн)
        свои.append(r)
    отметить(этап="старт", кампания=КАМП, получателей=len(свои),
             готово=0, брак=0)

    # кандидаты — ровно наш список, а не сегмент кампании
    уже = q._already(КАМП)
    q.candidates = lambda campaign_id, limit: [
        r for r in свои if r.id not in уже][:int(limit)]

    def пульс(ok, brak):
        отметить(этап="идёт", кампания=КАМП, получателей=len(свои),
                 готово=ok, брак=brak)

    # Квота дня считает и прошлые попытки кампании: перезапуск должен
    # прибавить свой список к уже сделанному, иначе «квота выбрана».
    до_ok, до_брак = q.counters(КАМП, [q.today()]).get(q.today(), (0, 0))
    рез = q.run_today(КАМП, quota=до_ok + до_брак + len(свои),
                      progress_cb=пульс)
    отметить(этап="готово", кампания=КАМП, получателей=len(свои),
             готово=рез.generated, брак=рез.rejected, причина=рез.reason,
             ошибок=len(рез.errors), ошибки=[str(e)[:160] for e in рез.errors[:15]])
except Exception as e:  # noqa: BLE001
    отметить(этап="упал", ошибка=str(e)[:300],
             след=traceback.format_exc()[-1500:])
