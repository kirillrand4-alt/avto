# -*- coding: utf-8 -*-
"""Только чтение: почему свободные прогретые ящики не берут писем."""
import datetime as dt
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.store import Store                # noqa: E402
from sender.suppression import Suppression    # noqa: E402
from sender.company_card import CompanyCards  # noqa: E402
import sender.sender as S                     # noqa: E402
import sender.gates as G                      # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)
g = G.Gates(cfg, store)
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
теперь = dt.datetime.now(dt.timezone.utc)
мейер = [m for m in cfg.get("mailboxes", []) if str(m.get("division")) == "meyer"]

print("=== РАЗБОР ПО КАЖДОМУ MEYER-ЯЩИКУ ===")
print("  %-34s %-6s %-6s %-6s %-7s %s"
      % ("ящик", "пауза", "гейт", "лимит", "пейсинг", "итог can_send_now"))
for m in мейер:
    mid = m["mailbox_id"]
    s = store.get_mailbox_state(mid)
    пауза = bool(getattr(s, "paused", False))
    гейт = g.check_mailbox(mid).tripped
    ключ = snd._day_key(теперь)
    if s is None:
        рамп, сег, посл = 0, 0, None
    elif s.day_key != ключ:
        рамп, сег, посл = (s.ramp_day or 0) + 1, 0, None
    else:
        рамп, сег, посл = s.ramp_day, s.sent_today, s.last_sent_at
    лим = snd._daily_limit(m.get("provider"), рамп, mid)
    лимит_ок = сег < лим
    пауз_сек = None
    if посл is not None:
        пауз_сек = (теперь - S._as_utc(посл)).total_seconds()
    пейс = "-" if пауз_сек is None else ("%.0fс" % пауз_сек)
    print("  %-34s %-6s %-6s %-6s %-7s %s"
          % (mid, "да" if пауза else "нет", "закр" if гейт else "ок",
             "%d/%d" % (сег, лим), пейс, snd.can_send_now(mid, now=теперь)))

print("\n=== ПУЛ ПОД КОНКРЕТНЫЕ ПИСЬМА ===")
камп11 = store.get_campaign(11)
камп12 = store.get_campaign(12)
for кид, камп in ((11, камп11), (12, камп12)):
    ряды = list(c.execute("SELECT id, recipient_id FROM messages WHERE campaign_id=?"
                          " AND status='scheduled' ORDER BY scheduled_at, id LIMIT 8",
                          (кид,)))
    print("  --- кампания %d ---" % кид)
    for р in ряды[:4]:
        rec = store.get_recipient(р["recipient_id"])
        msg = store.get_message(р["id"])
        пул = snd._route_pool(rec, камп)
        всп = cfg.provider_pools().get(пул, [])
        мвп = [x for x in всп if str({m["mailbox_id"]: m for m in мейер}
                                     .get(x, {}).get("division")) == "meyer"]
        годн = [x for x in мвп
                if snd.division_block(rec, x, message=msg) is None
                and snd.can_send_now(x, now=теперь)]
        print("    %-30s mx=%-8s пул=%-14s meyer в пуле %2d, годных %d %s"
              % (rec.email[:30], rec.mx_provider, пул, len(мвп), len(годн),
                 [x.split("@")[0] for x in годн[:3]]))
