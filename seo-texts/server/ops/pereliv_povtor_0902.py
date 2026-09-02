# -*- coding: utf-8 -*-
"""Только чтение: повторный замер перелива и ход партии."""
import datetime as dt
import sqlite3
import sys
from collections import Counter

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
камп = store.get_campaign(12)
ящ = {m["mailbox_id"]: m for m in cfg.get("mailboxes", [])}
c = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row

print("=== СКОЛЬКО ЗАПАСНЫХ MEYER СВОБОДНО ПРЯМО СЕЙЧАС ===")
зап = snd._zapasnye_yashchiki(cfg.provider_pools().get("pool_mailru", [])) or []
мз = [x for x in зап if str(ящ.get(x, {}).get("division")) == "meyer"]
своб = [x for x in мз if snd.can_send_now(x, now=теперь)]
print("  запасных всего %d, из них meyer %d, свободны сейчас %d"
      % (len(зап), len(мз), len(своб)))
print("  свободны: %s" % ", ".join(x.split("@")[0] for x in своб))

print("\n=== ЧТО ВЕРНЁТ ПОДБОР ДЛЯ MAIL.RU-ПИСЕМ ПАРТИИ ===")
ряды = list(c.execute(
    "SELECT m.id, m.recipient_id FROM messages m JOIN recipients r ON r.id=m.recipient_id"
    " WHERE m.campaign_id=12 AND m.status='scheduled' AND r.mx_provider='mailru'"))
итог = Counter()
for р in ряды:
    rec = store.get_recipient(р["recipient_id"])
    msg = store.get_message(р["id"])
    итог[snd.pick_mailbox(rec, камп, now=теперь, message=msg) or "НЕТ ЯЩИКА"] += 1
for k, v in итог.most_common():
    print("  %-38s %3d" % (k, v))

print("\n=== ХОД ПАРТИИ %s ===" % dt.datetime.now().strftime("%H:%M:%S"))
for р in c.execute("SELECT status, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " GROUP BY status"):
    print("  %-14s %d" % (р["status"], р["k"]))
print("  ушло по ящикам:")
for р in c.execute("SELECT mailbox_id, COUNT(*) k FROM messages WHERE campaign_id=12"
                   " AND status='sent' GROUP BY mailbox_id ORDER BY k DESC"):
    print("    %-36s %d" % (р["mailbox_id"], р["k"]))
Я = "i.kuznetsova@sort-systems.ru"
print("  письма Ирины: с её ящика %d, с чужого %d"
      % (c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                   " AND status='sent' AND body_rendered LIKE '%Ирина Кузнецова%'"
                   " AND mailbox_id=?", (Я,)).fetchone()[0],
         c.execute("SELECT COUNT(*) FROM messages WHERE campaign_id=12"
                   " AND status='sent' AND body_rendered LIKE '%Ирина Кузнецова%'"
                   " AND mailbox_id<>?", (Я,)).fetchone()[0]))
