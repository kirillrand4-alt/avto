# -*- coding: utf-8 -*-
"""Только чтение: что держит готовые письма Meyer от отправки.

Заслон спрашиваем у САМОГО конвейера (ConfirmSend._guard), а не пересчитываем
руками: ручной пересчёт уже давал ложные выводы. Ничего не меняет.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config          # noqa: E402
from sender.confirm import ConfirmSend    # noqa: E402
from sender.store import Store            # noqa: E402
from sender.suppression import Suppression  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))

import sqlite3  # noqa: E402
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

ряды = list(c.execute(
    "SELECT cr.id, cr.inn, cr.email, cr.status, m.status mst"
    "  FROM confirm_reviews cr LEFT JOIN messages m ON m.id = cr.message_id"
    " WHERE cr.campaign_id = 11 AND cr.status IN ('approved','pending')"
    "   AND (m.status IS NULL OR m.status NOT IN ('sent','skipped'))"))
print("=== Meyer: карточки, ещё НЕ ушедшие ===")
print("  всего таких: %d" % len(ряды))
print("  по статусу письма:", dict(Counter(str(r["mst"]) for r in ряды)))
print("  по статусу карточки:", dict(Counter(str(r["status"]) for r in ряды)))

print("\n=== опрос боевого заслона на первых 600 ===")
причины = Counter()
свободны = 0
for r in ряды[:600]:
    try:
        п = cs._guard(inn=str(r["inn"] or ""), email=str(r["email"] or ""))
    except Exception as e:
        причины["ОШИБКА ЗАСЛОНА: %s" % str(e)[:50]] += 1
        continue
    if п:
        причины[str(п).split(":")[0][:60]] += 1
    else:
        свободны += 1
print("  проверено: %d" % min(600, len(ряды)))
print("  СВОБОДНЫ (заслон молчит): %d" % свободны)
for k, v in причины.most_common(12):
    print("  %5d  %s" % (v, k))

print("\n=== ИТОГ ===")
print("  не ушедших карточек Meyer: %d" % len(ряды))
print("  из первых %d: свободны %d, заперты %d"
      % (min(600, len(ряды)), свободны, min(600, len(ряды)) - свободны))
