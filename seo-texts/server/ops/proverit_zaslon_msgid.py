# -*- coding: utf-8 -*-
"""Проверка выкатки: заслон по Message-ID работает, ничего не вставляя лишнего."""
import sqlite3
import sys
from datetime import datetime, timezone
sys.path.insert(0, r"C:\sender")
БАЗА = r"C:\sender\sender.db"
from sender.config import Config                                   # noqa: E402
from sender.dtos import EventIn                                    # noqa: E402
from sender.imap_watcher import ImapWatcher                        # noqa: E402
from sender.store import Store                                     # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", БАЗА))
print("в коде store есть _msgid_sobytiya: %s" % hasattr(Store, "_msgid_sobytiya"))
print("в коде опросчика есть _kogda_prishlo: %s"
      % hasattr(ImapWatcher, "_kogda_prishlo"))
print("дата из письма: %s"
      % ImapWatcher._kogda_prishlo({"Date": "Wed, 19 Aug 2026 09:46:13 +0300"}))
print("мусор вместо даты: %s (должно быть сегодня)"
      % ImapWatcher._kogda_prishlo({"Date": "вчера"}).strftime("%Y-%m-%d"))

c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
c.row_factory = sqlite3.Row
print("\nпокрытие Message-ID по типам:")
for r in c.execute("SELECT event_type, COUNT(*) n, "
                   "       SUM(rfc_msgid IS NOT NULL) est FROM events "
                   " WHERE event_type IN ('reply','reply_auto','bounce','complaint') "
                   " GROUP BY 1"):
    print("   %-12s всего %5d, с Message-ID %5d" % (r["event_type"], r["n"],
                                                    r["est"]))
проба = c.execute("SELECT mailbox_id, rfc_msgid, id FROM events "
                  " WHERE rfc_msgid IS NOT NULL AND mailbox_id IS NOT NULL "
                  " ORDER BY id LIMIT 1").fetchone()
до = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
c.close()
print("\nберём живое письмо: ev=%s ящик=%s" % (проба["id"], проба["mailbox_id"]))
eid, создали = store.append_event(EventIn(
    dedup_key="proverka:zaslon:%s" % проба["id"], event_type="reply",
    event_ts=datetime.now(timezone.utc), mailbox_id=проба["mailbox_id"],
    detail={"snippet": "проверка заслона",
            "headers": {"Message-ID": "<%s>" % проба["rfc_msgid"]}}))
c = sqlite3.connect("file:%s?mode=ro" % БАЗА, uri=True, timeout=60)
после = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
c.close()
print("повтор с тем же Message-ID: создано=%s, вернулся ev=%s (ожидали %s)"
      % (создали, eid, проба["id"]))
print("событий было %d, стало %d — %s"
      % (до, после, "ничего не вставлено" if после == до else "ВСТАВИЛОСЬ ЛИШНЕЕ"))
