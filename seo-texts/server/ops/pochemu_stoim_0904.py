# -*- coding: utf-8 -*-
"""Только чтение: почему очередь не двигается. Важное печатаем в конце."""
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
import sender.auto_send as A                  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карт = CompanyCards(index_path=str(cfg.get("obzvon.index_path", "") or "") or None,
                    enrich_db_path=str(cfg.get("obzvon.enrich_db", "") or "") or None)
snd = S.Sender(cfg, store, Suppression(store), G.Gates(cfg, store), cards=карт)
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
мск = dt.datetime.now()
utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

# ящики
теперь = dt.datetime.now(dt.timezone.utc)
своб = []
for m in cfg.get("mailboxes", []):
    if str(m.get("division")) != "meyer":
        continue
    if snd.can_send_now(m["mailbox_id"], now=теперь):
        своб.append(m["mailbox_id"])

# что возьмёт цикл
win = A.window_from(store, cfg)
проба = list(c.execute(
    "SELECT m.id, m.recipient_id, m.campaign_id FROM messages m"
    " WHERE m.status='scheduled' AND m.scheduled_at<=?"
    " AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id"
    " ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')"
    " ORDER BY m.scheduled_at, m.id LIMIT 10", (мск.isoformat(),)))
разбор = []
for р in проба:
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    зона = A.recipient_tz_name(win, rec)
    в_окне = A.within_window_now(win, зона, теперь)
    ящик = snd.pick_mailbox(rec, store.get_campaign(р["campaign_id"]),
                            now=теперь, message=msg) if в_окне else None
    разбор.append((р["id"], р["campaign_id"], rec.email, зона, в_окне, ящик))

print("=== ЧТО БУДЕТ С ПЕРВОЙ ДЕСЯТКОЙ ОЧЕРЕДИ ===")
for мид, кид, поч, зона, вок, ящик in разбор:
    print("  msg#%-6s к%-3s %-30s зона=%-18s в окне=%-5s ящик=%s"
          % (мид, кид, поч[:30], зона, вок, str(ящик).split("@")[0]))

print("\n=== ОКНО ===")
print("  %s" % win)
print("  сейчас %s МСК / %s UTC" % (мск.strftime("%H:%M"), utc.strftime("%H:%M")))
try:
    print("  окно для Москвы открыто: %s"
          % A.within_window_now(win, "Europe/Moscow", теперь))
except Exception as ex:
    print("  ошибка: %s" % str(ex)[:90])

print("\n=== ЯЩИКИ ===")
print("  meyer готовы слать: %d из 19" % len(своб))
print("  %s" % ", ".join(x.split("@")[0] for x in своб[:12]))

print("\n=== ОТПРАВКИ ===")
сут = utc.replace(hour=0, minute=0, second=0).isoformat()
print("  сегодня: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sent' AND sent_at>=?",
                  (сут,)).fetchone()[0])
п = c.execute("SELECT sent_at, campaign_id FROM messages WHERE status='sent'"
              " ORDER BY sent_at DESC LIMIT 1").fetchone()
print("  последняя: %s UTC (кампания %s)" % (str(п["sent_at"])[:19], п["campaign_id"]))
print("  висят в sending: %d"
      % c.execute("SELECT COUNT(*) FROM messages WHERE status='sending'").fetchone()[0])
print("  созрело и одобрено: %d" % c.execute(
    "SELECT COUNT(*) FROM messages m WHERE m.status='scheduled' AND m.scheduled_at<=?"
    " AND (SELECT cr.status FROM confirm_reviews cr WHERE cr.message_id=m.id"
    " ORDER BY cr.id DESC LIMIT 1) IN ('approved','edited')",
    (мск.isoformat(),)).fetchone()[0])
