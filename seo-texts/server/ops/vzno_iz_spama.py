# -*- coding: utf-8 -*-
"""Ответ «ВЗНО» лежит в спам-папке: достать и завести в ленту лидов.

Сторож читает только INBOX. 25.08 в 11:53 ООО «ВЗНО» ответило на наше
письмо, и почтовик положил ответ в «Спам» — в базе его нет, продавец его не
видел.

    python vzno_iz_spama.py            # показать письмо
    python vzno_iz_spama.py primenit   # завести лид
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ЯЩИК = "v.melnikov@kompressor-air-trade.ru"
ОТПРАВИТЕЛЬ = "deev@vzno.ru"

cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

rec = c.execute("SELECT id, email, company_name, inn FROM recipients "
                " WHERE lower(domain)='vzno.ru' OR lower(email) LIKE '%@vzno.ru'"
                ).fetchone()
print("получатель: #%s %s (%s)" % (rec["id"], rec["email"], rec["company_name"])
      if rec else "получателя нет")
есть = c.execute("SELECT id, event_type, event_ts FROM events "
                 " WHERE recipient_id=? AND event_type IN ('reply','reply_auto')",
                 (rec["id"],)).fetchall() if rec else []
print("ответов в базе: %d" % len(есть))
for e in есть:
    print("   #%s %s %s" % (e["id"], e["event_type"], str(e["event_ts"])[:19]))

д = mb.messages(ЯЩИК, folder="Spam", limit=20)
цель = None
for п in (д.get("messages") or []):
    if str(п.get("from_addr") or "").lower() == ОТПРАВИТЕЛЬ:
        цель = п
        break
if цель is None:
    print("письма в спаме не нашлось")
    raise SystemExit(0)
полное = mb.message(ЯЩИК, folder="Spam", uid=цель["uid"])
тело = " ".join(str(полное.get("body") or полное.get("text") or "").split())
print("")
print("=== письмо ===")
print("   от %s | %s" % (цель["from_addr"], цель["date_iso"]))
print("   тема: %s" % цель["subject"])
print("   текст: %s" % тело[:600])

if not ДЕЛАТЬ:
    print("\nвхолостую. Завести лид — primenit")
    raise SystemExit(0)

from sender.leaddesk import LeadDesk                          # noqa: E402
from sender.store import Store                                # noqa: E402

store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
десk = LeadDesk(cfg, store)
r = store.get_recipient(int(rec["id"]))
lid = десk.push_warm_lead(r, цель.get("message_id") or "",
                          "[reply] " + тело[:3000], otvetil=ОТПРАВИТЕЛЬ)
print("\nлид: %s" % lid)
c.close()
