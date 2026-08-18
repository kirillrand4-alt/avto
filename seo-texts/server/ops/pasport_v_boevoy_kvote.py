# -*- coding: utf-8 -*-
"""Тот же вопрос, но квота собрана ТАК ЖЕ, как в боевой генерации.

Прошлый замер я сделал неправильно: собрал AiQuota напрямую, без пути к
обогащению, и получил «паспорта нет» просто потому, что сам его не передал.
Боевой прогон строит квоту через build_ai_quota, где путь к enrich.db
берётся из конфига. Проверяем так же.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                        # noqa: E402
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
print("enrich_db у боевой квоты:", q._enrich_db)

with store._lock:
    ряд = store._conn.execute(
        "SELECT c.recipient_id, c.inn, c.id FROM confirm_reviews c "
        "WHERE c.campaign_id=10 AND c.recipient_id IS NOT NULL LIMIT 15"
    ).fetchall()

свод = Counter()
показан = False
for rid, inn, cid in ряд:
    r = store.get_recipient(int(rid))
    if r is None:
        continue
    try:
        зпр = q._request(r)
    except Exception as ex:                                       # noqa: BLE001
        свод[f"_request упал: {type(ex).__name__} {str(ex)[:60]}"] += 1
        continue
    п = ((зпр or {}).get("extra") or {}).get("site_facts") or {}
    непусто = any(п.get(k) for k in ("продукция", "мощности", "сырьё",
                                     "контроль_качества", "разбор_КЦ"))
    свод["паспорт в запросе ЕСТЬ" if непусто else "паспорта в запросе НЕТ"] += 1
    if непусто and not показан:
        показан = True
        print(f"\nпример #{cid} ИНН {inn}")
        for k in ("продукция", "мощности", "сырьё", "контроль_качества"):
            if п.get(k):
                print(f"  {k}: {str(п[k])[:180]}")
        рк = п.get("разбор_КЦ") or {}
        if рк:
            print(f"  разбор_КЦ: {str(рк)[:220]}")
print()
for к, n in свод.most_common():
    print(f"  {n:>4}  {к}")
