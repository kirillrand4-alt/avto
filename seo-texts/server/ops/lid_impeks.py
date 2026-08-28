# -*- coding: utf-8 -*-
"""Завести лид по горячему ответу «Импэкс-Дон» (событие 305587).

«тема очень актуальная по стационарным компрессорам, данной темой занимается
мой зам Поляков Виталий Валерьевич +7949 311 14 62» — событие легло типом
'other', и карточка не завелась.
"""
import sqlite3
import sys
sys.path.insert(0, r"C:\sender")
КАТИТЬ = "--katit" in sys.argv
ТЕКСТ = ("[interested, тел +7 949 311 14 62] Добрый день, тема очень актуальная "
         "по стационарным компрессорам. Данной темой занимается мой зам "
         "Поляков Виталий Валерьевич, +7 949 311 14 62 — проработайте этот "
         "вопрос с ним.")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402
from sender.leaddesk import LeadDesk                              # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
r = store.get_recipient(29417)
print("получатель: %s | %s" % (getattr(r, "email", "?"),
                              getattr(r, "company_name", "?")))
if not КАТИТЬ:
    raise SystemExit(0)
десk = LeadDesk(cfg, store)
ок = десk.push_warm_lead(getattr(r, "email", ""), None, ТЕКСТ,
                         otvetil="mail@impeks-don.ru")
print("push_warm_lead -> %r" % (ок,))
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
c.row_factory = sqlite3.Row
for x in c.execute("SELECT id, status, reply_kind, phone, company_name, need "
                   "  FROM leads WHERE recipient_id=29417 OR email=?",
                   (getattr(r, "email", ""),)):
    print("лид #%s | %s | %s | тел %s | %s" % (x["id"], x["status"], x["reply_kind"],
                                               x["phone"],
                                               str(x["company_name"] or "")[:34]))
    print("   %s" % str(x["need"] or "")[:170])
c.close()
