# -*- coding: utf-8 -*-
"""Только чтение: что стоит в расписании и уйдёт ли это сегодня."""
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

сейчас = dt.datetime.now()
сейчас_iso = сейчас.isoformat()
конец_дня = сейчас.replace(hour=23, minute=59, second=59).isoformat()
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("время панели: %s" % сейчас.strftime("%Y-%m-%d %H:%M"))

print("\n=== ОЧЕРЕДЬ ПО КАМПАНИЯМ ===")
for р in c.execute(
        "SELECT m.campaign_id, c.name, m.status, COUNT(*) n FROM messages m"
        " LEFT JOIN campaigns c ON c.id=m.campaign_id"
        " WHERE m.status IN ('scheduled','pending_review','sending')"
        " GROUP BY m.campaign_id, m.status ORDER BY m.campaign_id"):
    print("  #%-3s %-26s %-15s %4d"
          % (р["campaign_id"], str(р["name"])[:26], р["status"], р["n"]))

print("\n=== СОЗРЕЛИ К ОТПРАВКЕ (scheduled и срок уже наступил) ===")
созрели = list(c.execute(
    "SELECT m.id, m.campaign_id, m.recipient_id, m.mailbox_id FROM messages m"
    " WHERE m.status='scheduled' AND m.scheduled_at IS NOT NULL"
    " AND m.scheduled_at<=?", (сейчас_iso,)))
print("  всего: %d" % len(созрели))
по_камп = {}
for р in созрели:
    по_камп[р["campaign_id"]] = по_камп.get(р["campaign_id"], 0) + 1
for к, n in sorted(по_камп.items()):
    print("    кампания #%s: %d" % (к, n))

print("\n=== СОЗРЕЮТ ДО КОНЦА ДНЯ ===")
поздн = c.execute("SELECT COUNT(*) FROM messages WHERE status='scheduled'"
                  " AND scheduled_at>? AND scheduled_at<=?",
                  (сейчас_iso, конец_дня)).fetchone()[0]
print("  ещё: %d (в том числе наши 175 в 18:48)" % поздн)

print("\n=== ЕСТЬ ЛИ ЧЕМ СЛАТЬ ПРЯМО СЕЙЧАС ===")
теперь = dt.datetime.now(dt.timezone.utc)
свободно = []
for m in cfg.get("mailboxes", []):
    mid = m["mailbox_id"]
    try:
        если = snd.can_send_now(mid, now=теперь)
    except Exception:
        если = False
    if если:
        свободно.append((str(m.get("division")), mid))
print("  ящиков готовы слать: %d (meyer %d, kc %d)"
      % (len(свободно), sum(1 for d, _ in свободно if d == "meyer"),
         sum(1 for d, _ in свободно if d == "kc")))
print("  внутри окна отправки: %s" % snd._within_window(dt.datetime.now().astimezone()))

print("\n=== СКОЛЬКО ФИЗИЧЕСКИ УСПЕЕТ УЙТИ ===")
шаг_мин = int(cfg.get("send_pacing.min_interval_sec", 90) or 90)
шаг_макс = int(cfg.get("send_pacing.max_interval_sec", 420) or 420)
окно_кон = сейчас.replace(hour=18, minute=0, second=0)
часов = max(0.0, (окно_кон - сейчас).total_seconds() / 3600.0)
средний = (шаг_мин + шаг_макс) / 2.0
print("  пейсинг %d..%d сек на письмо, до 18:00 осталось %.1f ч"
      % (шаг_мин, шаг_макс, часов))
print("  потолок по темпу: примерно %d писем за остаток дня"
      % int(часов * 3600 / средний))

print("\n=== ЧТО УШЛО СЕГОДНЯ ===")
утро = сейчас.replace(hour=0, minute=0, second=0).isoformat()
n = c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
              (утро,)).fetchone()[0]
print("  отправлено с полуночи: %d" % n)
for р in c.execute("SELECT mailbox_id, COUNT(*) n FROM messages WHERE status='sent'"
                   " AND sent_at>=? GROUP BY mailbox_id ORDER BY n DESC LIMIT 8",
                   (утро,)):
    print("    %-34s %d" % (р["mailbox_id"], р["n"]))
