# -*- coding: utf-8 -*-
"""Случайная выборка писем из очереди — читать глазами.

Баланс шлюза пуст, линзу гонять нечем. Смотрим сами: берём письма из
разных эпох очереди (старые опусовые и свежие sonnet), печатаем с
паспортом компании рядом, чтобы видеть, не выдуманы ли факты.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender\sender")
sys.path.insert(0, r"C:\sender")

from sender.ai_quota import build_ai_quota                    # noqa: E402
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
q = build_ai_quota(store, cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "8"))
строки = c.execute(
    "SELECT cr.id, cr.subject, cr.body, cr.created_at, r.company_name, "
    "       r.okved, r.inn, m.campaign_id, m.status mst "
    "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status IN ('approved','pending') AND COALESCE(cr.body,'')<>'' "
    " ORDER BY RANDOM() LIMIT ?", (СКОЛЬКО,)).fetchall()

for р in строки:
    напр = "meyer" if р["campaign_id"] == 11 else "kc"
    print("\n" + "=" * 78)
    print("#%s | %s | создано %s | письмо=%s | НАПРАВЛЕНИЕ %s"
          % (р["id"], str(р["company_name"] or "")[:44],
             str(р["created_at"])[:16], р["mst"], напр.upper()))
    print("ОКВЭД: %s" % str(р["okved"] or "-")[:70])
    try:
        п = q._site_facts(р["inn"]) or {}
    except Exception:  # noqa: BLE001
        п = {}
    for к in ("продукция", "оборудование_линии", "сырьё"):
        v = п.get(к)
        if v:
            т = v if isinstance(v, str) else "; ".join(map(str, v))
            print("  паспорт/%s: %s" % (к, т[:130]))
    print("-" * 78)
    print("ТЕМА: %s" % р["subject"])
    print(р["body"])
