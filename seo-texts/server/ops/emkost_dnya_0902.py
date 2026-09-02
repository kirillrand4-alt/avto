# -*- coding: utf-8 -*-
"""Только чтение: идёт ли отправка, в каком порядке и на сколько хватит лимитов."""
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
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
теперь = dt.datetime.now(dt.timezone.utc)
у = сейчас.replace(hour=0, minute=0, second=0).isoformat()

print("время %s" % сейчас.strftime("%H:%M:%S"))
print("отправлено сегодня всего: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                  (у,)).fetchone()[0])
посл = c.execute("SELECT sent_at, mailbox_id, campaign_id FROM messages"
                 " WHERE status='sent' ORDER BY sent_at DESC LIMIT 3").fetchall()
for р in посл:
    print("  последнее: %s | %s | кампания %s"
          % (str(р["sent_at"])[11:19], р["mailbox_id"], р["campaign_id"]))

print("\n=== ПОРЯДОК ОЧЕРЕДИ (кого возьмут первыми) ===")
try:
    print("  claim_approved_due: %s"
          % str(inspect.signature(store.claim_approved_due))[:90])
    исх = inspect.getsource(store.claim_approved_due)
    for л in исх.splitlines():
        if "ORDER BY" in л.upper():
            print("  %s" % л.strip()[:100])
except Exception as ex:
    print("  %s" % str(ex)[:100])
for р in c.execute(
        "SELECT m.campaign_id, MIN(m.scheduled_at) старт, COUNT(*) k FROM messages m"
        " WHERE m.status='scheduled' AND m.scheduled_at<=?"
        " AND EXISTS (SELECT 1 FROM confirm_reviews cr WHERE cr.message_id=m.id"
        " AND cr.status IN ('approved','edited')) GROUP BY m.campaign_id",
        (сейчас.isoformat(),)):
    print("  кампания %-3s срок с %s — %d писем"
          % (р["campaign_id"], str(р["старт"])[:16], р["k"]))

print("\n=== ЁМКОСТЬ MEYER-ЯЩИКОВ НА СЕГОДНЯ ===")
итого = 0
for m in cfg.get("mailboxes", []):
    if str(m.get("division")) != "meyer":
        continue
    mid = m["mailbox_id"]
    s = store.get_mailbox_state(mid)
    сег = getattr(s, "sent_today", 0) or 0
    ключ = snd._day_key(теперь)
    if s is not None and s.day_key != ключ:
        рамп, сег = (s.ramp_day or 0) + 1, 0
    else:
        рамп = getattr(s, "ramp_day", 0) or 0
    лим = snd._daily_limit(m.get("provider"), рамп, mid)
    пауза = bool(getattr(s, "paused", False))
    ост = 0 if пауза else max(0, лим - сег)
    итого += ост
    print("  %-36s ramp=%-3s лимит=%-4s ушло=%-3s остаток=%-4s%s"
          % (mid, рамп, лим, сег, ост, " ПАУЗА" if пауза else ""))
print("  ИТОГО ёмкость meyer на сегодня: %d писем" % итого)
print("  в очереди meyer (кампании 11 и 12): %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled'"
                  " AND campaign_id IN (11,12)").fetchone()[0])
