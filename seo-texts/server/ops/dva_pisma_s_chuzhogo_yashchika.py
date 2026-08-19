# -*- coding: utf-8 -*-
"""Письма кампании 10, ушедшие с мейеровских ящиков: что это было."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.confirm import ConfirmSend                           # noqa: E402
from sender.store import Store                                   # noqa: E402
from sender.suppression import Suppression                       # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
cs = ConfirmSend(cfg, store, Suppression(store))
мейер = {mb.mailbox_id for mb in cfg.mailboxes()
         if "meyer" in str(getattr(mb, "division", "") or "").lower()}

with store._lock:
    ряды = store._conn.execute(
        """SELECT c.id, m.mailbox_id, m.sent_at, COALESCE(m.subject,''),
                  COALESCE(c.body,''), COALESCE(rc.company_name,'')
             FROM messages m
             JOIN confirm_reviews c ON c.message_id=m.id
             LEFT JOIN recipients rc ON rc.id=c.recipient_id
            WHERE c.campaign_id=10 AND m.status='sent'
              AND date(m.sent_at)=date('now')""").fetchall()
найдено = 0
for rid, ящик, когда, тема, тело, фирма in ряды:
    if ящик not in мейер:
        continue
    найдено += 1
    d = ""
    try:
        d = cs.letter_division(store.confirm_get(rid) or {}) or "?"
    except Exception:                                            # noqa: BLE001
        d = "?"
    print(f"#{rid}  ушло {str(когда)[11:19]} с {ящик}")
    print(f"  фирма: {фирма[:50]}")
    print(f"  направление письма по панели: {d}")
    print(f"  тема: {тема}")
    print(f"  тело: {тело[:300]}\n")
print(f"всего таких: {найдено} из {len(ряды)} отправленных сегодня по КЦ")
