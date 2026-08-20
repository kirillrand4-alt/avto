# -*- coding: utf-8 -*-
"""Что за 49 карточек старых кампаний 7-9 и есть ли у них паспорт сайта.

Владелец 20.08: «если ещё не было профиля компании, тогда перепиши с
профилем, либо скипни чтобы ждать пока появится профиль».

Значит надо знать по каждой: когда письмо написано, есть ли сейчас
паспорт сайта (его собирает обогащение) и проходит ли адрес заслоны.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

with store._lock:
    ряды = store._conn.execute(
        "SELECT c.id, c.campaign_id, c.recipient_id, c.email, c.created_at, "
        "       r.company_name, r.inn, COALESCE(r.okved,'') okved "
        "FROM confirm_reviews c LEFT JOIN recipients r ON r.id=c.recipient_id "
        "WHERE c.status='pending' AND c.campaign_id NOT IN (10,11) "
        "ORDER BY c.id").fetchall()

print(f"карточек: {len(ряды)}")
print("по кампаниям:", dict(Counter(int(r["campaign_id"]) for r in ряды)))
print("по дате письма:", dict(Counter(str(r["created_at"] or "")[:10]
                                      for r in ряды)))

счёт = Counter()
для_показа = []
for r in ряды:
    инн = str(r["inn"] or "")
    try:
        д = q._site_facts(инн) or {}
    except Exception:                                            # noqa: BLE001
        д = {}
    полей = sum(1 for k in ("цитата", "продукция", "оборудование_линии",
                            "сырьё", "масштаб", "мощности") if д.get(k))
    счёт["паспорт есть" if полей else "паспорта НЕТ"] += 1
    для_показа.append((int(r["id"]), str(r["company_name"] or "")[:32],
                       полей, str(r["okved"] or "")[:8]))

for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
print()
for i, (rid, имя, полей, ок) in enumerate(для_показа):
    if i >= 50:
        break
    print(f"  #{rid} {имя:<32} паспорт-полей={полей} оквэд={ок}")
