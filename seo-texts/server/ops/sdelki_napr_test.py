# -*- coding: utf-8 -*-
"""Проверка заслона сделок по направлениям без отправки + снять из очереди письма
под запретом (--snyat, штатно confirm_decide skipped).

На примерах ИНН: только Meyer / только КЦ / только СЦ — что скажут модуль,
флаг карточки (_division_flags) для кампаний Meyer и КЦ.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config  # noqa: E402
from sender.sdelki_napr import blok  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.wiring import build_deps  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
d = build_deps(cfg, store, dry_run=True)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
камп_kc = next((r[0] for r in c.execute("SELECT id FROM campaigns WHERE name LIKE '%КЦ%' ORDER BY id DESC")), None)
for что, sql in (("только Meyer", "meyer=1 AND kc=0"), ("только КЦ", "meyer=0 AND kc=1"),
                 ("только СЦ", "meyer=0 AND kc=0 AND sc=1"), ("Meyer+КЦ", "meyer=1 AND kc=1")):
    inn = (c.execute("SELECT inn FROM sdelki_napr WHERE %s LIMIT 1" % sql).fetchone() or [None])[0]
    фл_m = [f["code"] for f in d.confirm._division_flags(inn=inn, campaign_id=14)]
    фл_k = [f["code"] for f in d.confirm._division_flags(inn=inn, campaign_id=камп_kc)] if камп_kc else "-"
    print("%-12s ИНН %s | модуль: meyer=%s kc=%s | флаги карточки: Meyer-кампания %s, КЦ-кампания %s"
          % (что, inn, bool(blok(c, inn, "meyer")), bool(blok(c, inn, "kc")), фл_m, фл_k))
под = []
for rid, inn, cid in c.execute("SELECT id, inn, campaign_id FROM confirm_reviews WHERE status='pending'"):
    if any(f.get("code") == "deal_in_division" for f in d.confirm._division_flags(inn=inn, campaign_id=cid)):
        под.append(rid)
print("в очереди под запретом сделки: %d" % len(под))
if "--snyat" in sys.argv:
    n = sum(bool(store.confirm_decide(r, status="skipped", reason="сделка в работе по направлению (владелец 14.10)",
                                      decided_by="claude-ops")) for r in под)
    print("снято из очереди: %d" % n)
print("=== ТЕСТ СДЕЛОК ===")
