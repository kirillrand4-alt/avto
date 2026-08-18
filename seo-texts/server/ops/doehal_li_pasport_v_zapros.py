# -*- coding: utf-8 -*-
"""Доезжает ли паспорт сайта до ЗАПРОСА генерации (а не до панели оператора).

Панель оператора и запрос генерации — разные структуры. То, что в
panel_json нет site_facts, ещё не значит, что его не было в промпте.
Спрашиваем прямо: собираем запрос тем же кодом, что и генератор.
"""
import json
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.wiring import build_deps                             # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
deps = build_deps(cfg, store, dry_run=True)
q = getattr(deps, "ai_quota", None)
if q is None:
    from sender.ai_quota import AiQuota
    q = AiQuota(config=cfg, store=store)
print("enrich_db у квоты:", getattr(q, "_enrich_db", "(нет атрибута)"))

with store._lock:
    ряд = store._conn.execute(
        "SELECT c.recipient_id, c.inn, c.id FROM confirm_reviews c "
        "WHERE c.campaign_id=10 AND c.recipient_id IS NOT NULL LIMIT 12"
    ).fetchall()

свод = Counter()
for rid, inn, cid in ряд:
    r = store.get_recipient(int(rid))
    if r is None:
        свод["нет получателя"] += 1
        continue
    try:
        зпр = q._request(r)
    except Exception as ex:                                      # noqa: BLE001
        свод[f"_request упал: {type(ex).__name__}"] += 1
        continue
    ex_ = (зпр or {}).get("extra") or {}
    п = ex_.get("site_facts") or {}
    непусто = any(п.get(k) for k in ("продукция", "мощности", "сырьё",
                                     "контроль_качества", "разбор_КЦ"))
    свод["паспорт в запросе ЕСТЬ" if непусто else "паспорта в запросе НЕТ"] += 1
    if непусто and свод["паспорт в запросе ЕСТЬ"] == 1:
        print(f"\nпример #{cid} ИНН {inn}:")
        print("  продукция:", str(п.get("продукция"))[:200])
        print("  мощности: ", str(п.get("мощности"))[:150])
        print("  разбор_КЦ:", str(п.get("разбор_КЦ"))[:200])
    if not непусто and свод["паспорта в запросе НЕТ"] == 1:
        print(f"\nбез паспорта: #{cid} ИНН {inn}, "
              f"ключи extra: {sorted(ex_)[:12]}")

print()
for к, n in свод.most_common():
    print(f"  {n:>4}  {к}")
