# -*- coding: utf-8 -*-
"""Едут ли мейеровские письма: очередь, ящики, лимиты, что мешает."""
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                 # noqa: E402
from sender.ramp import curve_value                              # noqa: E402
from sender.store import Store                                   # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))

print("== письма кампании 11 ==")
with store._lock:
    по_реш = store._conn.execute(
        "SELECT status, COUNT(*) FROM confirm_reviews WHERE campaign_id=11 "
        "GROUP BY status").fetchall()
    по_письм = store._conn.execute(
        "SELECT m.status, COUNT(*) FROM messages m "
        "JOIN confirm_reviews c ON c.message_id=m.id "
        "WHERE c.campaign_id=11 GROUP BY m.status").fetchall()
    ждут = store._conn.execute(
        "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
        "ON c.message_id=m.id WHERE c.campaign_id=11 "
        "AND c.status='approved' AND m.status='scheduled'").fetchone()[0]
    ушло = store._conn.execute(
        "SELECT COUNT(*) FROM messages m JOIN confirm_reviews c "
        "ON c.message_id=m.id WHERE c.campaign_id=11 AND m.status='sent' "
        "AND date(m.sent_at)=date('now')").fetchone()[0]
print("  решения:", dict(по_реш))
print("  письма: ", dict(по_письм))
print(f"  ЖДУТ ОТПРАВКИ: {ждут} | ушло сегодня: {ушло}")

print("\n== мейеровские ящики ==")
try:
    ящики = cfg.mailboxes()
except Exception as ex:                                          # noqa: BLE001
    ящики = []
    print("  ящики не прочитались:", str(ex)[:90])
лимиты = (store.get_setting("send_limits") or {}) if hasattr(
    store, "get_setting") else {}
per = (лимиты or {}).get("per_mailbox") or {}
for mb in ящики:
    div = str(getattr(mb, "division", "") or "")
    if "meyer" not in div.lower():
        continue
    mid = mb.mailbox_id
    день = 0
    try:
        день = store.sent_today(mid) if hasattr(store, "sent_today") else 0
    except Exception:                                            # noqa: BLE001
        pass
    рамп = getattr(mb, "ramp_day", None)
    print(f"  {mid:<40} рамп-день {рамп} | ручной потолок "
          f"{per.get(mid, '—')} | отправлено сегодня {день}")

print("\n== окно отправки ==")
print(" ", store.get_setting("sending_window"))
