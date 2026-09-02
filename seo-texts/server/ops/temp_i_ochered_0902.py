# -*- coding: utf-8 -*-
"""Только чтение: темп, порядок очереди и успеет ли партия до 14:00."""
import datetime as dt
import sqlite3

c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
сейчас = dt.datetime.now()
у = сейчас.replace(hour=0, minute=0, second=0).isoformat()

print("=== ПОРЯДОК ОЧЕРЕДИ: КТО ВПЕРЕДИ ===")
now_iso = сейчас.isoformat()
sql = """SELECT m.campaign_id, m.scheduled_at FROM messages m
         WHERE m.status='scheduled' AND m.scheduled_at <= ?
           AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id
                 ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')
         ORDER BY m.scheduled_at, m.id LIMIT 60"""
ряды = list(c.execute(sql, (now_iso,)))
из12 = sum(1 for р in ряды if р["campaign_id"] == 12)
print("  в первых 60 очереди: кампании 12 — %d, кампании 11 — %d"
      % (из12, len(ряды) - из12))
print("  первые пять сроков: %s" % [str(р["scheduled_at"])[:16] for р in ряды[:5]])
print("  сроки кампании 11 в очереди:")
for р in c.execute("SELECT substr(scheduled_at,1,10) д, COUNT(*) k FROM messages"
                   " WHERE campaign_id=11 AND status='scheduled'"
                   " GROUP BY д ORDER BY д LIMIT 6"):
    print("    %s  %d" % (р["д"], р["k"]))

print("\n=== ТЕМП ЗА ПОСЛЕДНИЕ 15 МИНУТ ===")
п15 = (сейчас - dt.timedelta(minutes=15)).isoformat()
n15 = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                (п15,)).fetchone()[0]
print("  ушло за 15 мин: %d (%.1f писем/мин)" % (n15, n15 / 15.0))
n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
              (у,)).fetchone()[0]
print("  за сегодня всего: %d" % n)
осталось_мин = (сейчас.replace(hour=14, minute=0, second=0) - сейчас).total_seconds() / 60
print("  до 14:00 минут: %d, при текущем темпе успеет ещё %d писем"
      % (осталось_мин, int(осталось_мин * n15 / 15.0)))

print("\n=== ЁМКОСТЬ, КОТОРАЯ ОСТАЛАСЬ ===")
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
теперь = dt.datetime.now(dt.timezone.utc)
итого = 0
for m in cfg.get("mailboxes", []):
    if str(m.get("division")) != "meyer":
        continue
    s = store.get_mailbox_state(m["mailbox_id"])
    if getattr(s, "paused", False):
        continue
    ключ = snd._day_key(теперь)
    рамп = (s.ramp_day or 0) + (0 if (s and s.day_key == ключ) else 1) if s else 0
    сег = s.sent_today if (s and s.day_key == ключ) else 0
    итого += max(0, snd._daily_limit(m.get("provider"), рамп, m["mailbox_id"]) - сег)
print("  свободный дневной остаток meyer-ящиков: %d писем" % итого)
print("  нашей партии осталось отправить: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                  " AND status='scheduled'").fetchone()[0])
