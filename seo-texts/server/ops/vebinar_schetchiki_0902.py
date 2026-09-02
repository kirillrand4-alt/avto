# -*- coding: utf-8 -*-
"""Только чтение: счётчики дня по meyer-ящикам и почему can_send_now отказывает."""
import datetime as dt
import inspect
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

сейчас = dt.datetime.now(dt.timezone.utc)
ключ_дня = snd._day_key(сейчас)
print("день по версии движка: %s | локально: %s"
      % (ключ_дня, dt.datetime.now().strftime("%Y-%m-%d %H:%M")))

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
неделя = (dt.datetime.now() - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
факт = {}
for р in c.execute("SELECT mailbox_id, COUNT(*) n FROM messages WHERE status='sent'"
                   " AND sent_at>=? GROUP BY mailbox_id", (неделя,)):
    факт[р["mailbox_id"]] = р["n"]

print(inspect.getsource(S.Sender.can_send_now)[-900:])
print("\n%-34s %-11s %-6s %-6s %-5s %-6s %s"
      % ("ящик", "day_key", "сег", "лимит", "ramp", "факт24", "можно слать"))
for m in cfg.get("mailboxes", []):
    if str(m.get("division")) != "meyer":
        continue
    mid = m["mailbox_id"]
    s = store.get_mailbox_state(mid)
    try:
        можно = snd.can_send_now(mid, now=сейчас)
    except Exception as ex:
        можно = "ошибка %s" % str(ex)[:30]
    протух = (s is not None and s.day_key != ключ_дня)
    print("%-34s %-11s %-6s %-6s %-5s %-6s %s%s"
          % (mid, getattr(s, "day_key", "-"), getattr(s, "sent_today", "-"),
             getattr(s, "daily_limit", "-"), getattr(s, "ramp_day", "-"),
             факт.get(mid, 0), можно,
             "   <-- СЧЁТЧИК СО ВЧЕРА" if протух else ""))

