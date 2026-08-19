# -*- coding: utf-8 -*-
"""Почему опус на панельном пути ПИШЕТ кэш каждый раз и не читает.

Скриншот шлюза от владельца: на каждом вызове opus «Кэш ↓ 40 ↑ 17 998» -
восемнадцать тысяч токенов записи и сорок чтения. Рядом sonnet читает
12 595. Значит статическая часть промпта у писем РАЗНАЯ от вызова к вызову,
и шлюз каждый раз кладёт новый кэш вместо того, чтобы читать старый.

Проверяем прямо: собираем промпт перегенерации для ДВУХ разных писем и
сравниваем их левые части побайтно.
"""
import sys

sys.path.insert(0, r"C:\sender")
import gen_provider as GP                                        # noqa: E402
from sender.ai_quota import build_ai_quota                       # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)

with store._lock:
    ряды = store._conn.execute(
        "SELECT id FROM confirm_reviews WHERE status='pending' "
        "AND campaign_id IN (10,11) ORDER BY id DESC LIMIT 2").fetchall()
ид = [r[0] for r in ряды]
print("письма для сравнения:", ид)

статики = []
for rid in ид:
    row = store.confirm_get(int(rid)) or {}
    rec = store.get_recipient(int(row.get("recipient_id") or 0))
    if not rec:
        print(f"#{rid}: получателя нет")
        continue
    req = q._request(rec)
    from sender.ai_letter import gen_prompt, load_facts          # noqa: E402
    div = str(req.get("target_division") or "kc")
    п = gen_prompt([req], load_facts(division=div), div, angle_base=0)
    с, т = GP.razrezat_promt(п)
    статики.append((rid, с or "", т or ""))
    print(f"#{rid}: промпт {len(п)} знаков, статика {len(с or '')}, "
          f"переменная {len(т or '')}")

if len(статики) == 2:
    a, b = статики[0][1], статики[1][1]
    print(f"\nстатические части СОВПАДАЮТ: {a == b}")
    if a != b:
        # где расходятся
        i = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]),
                 min(len(a), len(b)))
        print(f"расходятся с {i}-го знака из {len(a)}")
        print("  первая:  …" + a[max(0, i - 90):i + 90].replace("\n", "⏎"))
        print("  вторая:  …" + b[max(0, i - 90):i + 90].replace("\n", "⏎"))
