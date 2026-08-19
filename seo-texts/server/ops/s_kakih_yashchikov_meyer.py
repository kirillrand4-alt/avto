# -*- coding: utf-8 -*-
"""С каких ящиков уходят мейеровские письма.

Мейеровское письмо обязано уходить с мейеровского ящика: подпись, домен и
бренд в нём свои. Если оно уедет с компрессорного - получатель увидит
письмо про сортировку за подписью менеджера Компрессор Центра.
"""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
напр = {}
try:
    for mb in cfg.mailboxes():
        напр[mb.mailbox_id] = str(getattr(mb, "division", "") or "?")
except Exception as ex:                                          # noqa: BLE001
    print("ящики не прочитались:", str(ex)[:80])

for камп, имя in ((11, "Meyer"), (10, "КЦ")):
    with store._lock:
        ряды = store._conn.execute(
            "SELECT COALESCE(m.mailbox_id,'—'), COUNT(*) FROM messages m "
            "JOIN confirm_reviews c ON c.message_id=m.id "
            "WHERE c.campaign_id=? AND m.status='sent' "
            "AND date(m.sent_at)=date('now') GROUP BY 1 ORDER BY 2 DESC",
            (камп,)).fetchall()
    print(f"\n== кампания {камп} ({имя}), отправлено сегодня ==")
    if not ряды:
        print("  сегодня ничего не ушло")
    for ящик, n in ряды:
        d = напр.get(ящик, "?")
        метка = "" if (имя.lower()[:5] in d.lower()) else "  <-- ЧУЖОЙ ЯЩИК"
        print(f"  {n:>4}  {ящик:<42} направление {d}{метка}")
