# -*- coding: utf-8 -*-
"""Промпт письма для ВТОРОГО варианта (best-of-N) - со сдвигом механики.

Боевой конвейер делает best_of=2: второй заход идёт тем же gen_prompt, но
с angle_base = n + att*3, и это назначает получателю ДРУГУЮ механику
захода. Просто повторный вызов того же промпта вариантом не считается -
он даст то же самое. Поэтому промпт пересобираем честно.

Запуск: promt_variant.py N угол [часть] [размер]
"""
import io
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import gen_prompt, load_facts                   # noqa: E402
from sender.ai_quota import build_ai_quota                            # noqa: E402
from sender.config import Config                                      # noqa: E402
from sender.store import Store                                        # noqa: E402

н = int(sys.argv[1]) if len(sys.argv) > 1 else 0
угол = int(sys.argv[2]) if len(sys.argv) > 2 else 3
часть = int(sys.argv[3]) if len(sys.argv) > 3 else 0
размер = int(sys.argv[4]) if len(sys.argv) > 4 else 4000

данные = json.load(io.open(r"C:\sender\_ops\promty10.json", encoding="utf-8"))
з = данные[н]
инн = з["inn"]

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
rec = None
for эл in (q.candidates(10, limit=400) or []):
    r = эл[1] if isinstance(эл, (tuple, list)) else эл
    if str(getattr(r, "inn", "")) == инн:
        rec = r
        break
if rec is None:
    print(f"получатель с ИНН {инн} не найден среди кандидатов")
    raise SystemExit(0)

т = gen_prompt([q._request(rec)], load_facts(division="kc"), "kc",
               angle_base=угол)
всего = (len(т) + размер - 1) // размер
print(f"### ВАРИАНТ угол={угол} ПРОМПТ {н}: {з['company']} | {з['email']}")
print(f"### знаков {len(т)}, частей по {размер}: {всего}")
if часть:
    к = часть - 1
    print(f"### ЧАСТЬ {часть} из {всего}")
    print(т[к * размер:(к + 1) * размер])
else:
    print(т[:размер])
