# -*- coding: utf-8 -*-
"""Сколько писем не хватает до полной загрузки ящиков сегодня.

Ёмкость дня считается рампом каждого ящика (Sender._daily_limit), а не
общим числом. Дальше вычитаем то, что уже ушло, и то, что готово уйти.
"""
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.company_card import CompanyCards                     # noqa: E402
from sender.config import Config                                 # noqa: E402
from sender.gates import Gates                                   # noqa: E402
from sender.sender import Sender                                 # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
snd = Sender(cfg, store, Suppression(store), Gates(cfg, store), dry_run=True,
             cards=CompanyCards(
                 index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                 enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "")
                 or None))
сегодня = datetime.now(timezone.utc).date().isoformat()

ёмкость, ящиков = Counter(), Counter()
for mb in cfg.mailboxes():
    div = str(getattr(mb, "division", "") or "").lower()
    напр = "Meyer" if ("meyer" in div or "мейер" in div) else "КЦ"
    st = store.get_mailbox_state(mb.mailbox_id)
    рд = getattr(st, "ramp_day", 0) if st else 0
    ёмкость[напр] += snd._daily_limit(mb.provider, рд + 1, mb.mailbox_id)
    ящиков[напр] += 1

ушло, готово = Counter(), Counter()
with store._lock:
    for camp, имя in ((10, "КЦ"), (9, "КЦ"), (11, "Meyer"), (7, "Meyer"),
                      (8, "Meyer")):
        ушло[имя] += store._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE campaign_id=? "
            "AND status='sent' AND substr(updated_at,1,10)=?",
            (camp, сегодня)).fetchone()[0]
        готово[имя] += store._conn.execute(
            "SELECT COUNT(*) FROM messages m JOIN confirm_reviews cr "
            "ON cr.message_id=m.id WHERE m.campaign_id=? "
            "AND cr.status IN ('approved','edited') "
            "AND m.status IN ('scheduled','sending')",
            (camp,)).fetchone()[0]
    в_ocheredi = Counter()
    for camp, имя in ((10, "КЦ"), (9, "КЦ"), (11, "Meyer"), (7, "Meyer"),
                      (8, "Meyer")):
        в_ocheredi[имя] += store._conn.execute(
            "SELECT COUNT(*) FROM confirm_reviews WHERE campaign_id=? "
            "AND status='pending'", (camp,)).fetchone()[0]

print(f"{'':<8} {'ящиков':>7} {'ёмкость':>8} {'ушло':>6} {'готово':>7} "
      f"{'НЕ ХВАТАЕТ':>11} {'в очереди подтв.':>17}")
итого = 0
for имя in ("КЦ", "Meyer"):
    е, у, г = ёмкость[имя], ушло[имя], готово[имя]
    не_хватает = max(0, е - у - г)
    итого += не_хватает
    print(f"{имя:<8} {ящиков[имя]:>7} {е:>8} {у:>6} {г:>7} "
          f"{не_хватает:>11} {в_ocheredi[имя]:>17}")
print(f"\nвсего не хватает до полной загрузки: {итого}")
print("(«готово» — одобренные со слотом; «в очереди подтв.» — написаны, "
      "но ещё не одобрены)")
