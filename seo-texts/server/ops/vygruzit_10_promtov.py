# -*- coding: utf-8 -*-
"""Выгрузить 10 настоящих промптов письма КЦ - для замера на агентах.

Собираем ровно то, что уходит провайдеру: q._request(rec) плюс
ai_letter.gen_prompt. Своего упрощённого промпта не сочиняем, иначе
замер будет не про наши письма, а про придуманную задачу.
"""
import io
import json
import sys

sys.path.insert(0, r"C:\sender")
from sender.ai_letter import gen_prompt, load_facts, target_division  # noqa: E402
from sender.ai_quota import build_ai_quota                            # noqa: E402
from sender.config import Config                                      # noqa: E402
from sender.store import Store                                        # noqa: E402

СКОЛЬКО = int(sys.argv[1]) if len(sys.argv) > 1 else 10
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
факты = load_facts(division="kc")

пары = q.candidates(10, limit=СКОЛЬКО * 12) or []   # 10 — кампания КЦ
print(f"кандидатов взято: {len(пары)}")
готово = []
for эл in пары:
    if len(готово) >= СКОЛЬКО:
        break
    rec = эл[1] if isinstance(эл, (tuple, list)) else эл
    try:
        req = q._request(rec)
    except Exception as ex:                                       # noqa: BLE001
        continue
    д = req.get("target_division")
    if not д:
        try:
            д = (target_division(req) or ("kc",))[0]
        except Exception:                                          # noqa: BLE001
            д = "kc"
    if str(д).lower() != "kc":
        continue
    try:
        промпт = gen_prompt([req], факты, "kc", angle_base=len(готово))
    except Exception as ex:                                        # noqa: BLE001
        print(f"  промпт не собрался: {type(ex).__name__} {str(ex)[:70]}")
        continue
    готово.append({"inn": str(getattr(rec, "inn", "")),
                   "company": getattr(rec, "company_name", ""),
                   "email": getattr(rec, "email", ""),
                   "promt": промпт})

путь = r"C:\sender\_ops\promty10.json"
io.open(путь, "w", encoding="utf-8").write(
    json.dumps(готово, ensure_ascii=False, indent=1))
знаков = sum(len(г["promt"]) for г in готово)
print(f"\nсобрано промптов: {len(готово)}")
print(f"знаков всего: {знаков}, в среднем на письмо: "
      f"{знаков // max(1, len(готово))}")
print(f"файл: {путь}")
for г in готово[:3]:
    print(f"  {г['company'][:38]:38} {г['email']}")
