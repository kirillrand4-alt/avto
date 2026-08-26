# -*- coding: utf-8 -*-
"""Дописать событие «reply» по ответу «ВЗНО»: карточка письма его не видит.

История переписки на карточке письма строится из events (dialog_thread), а
достав ответ из спама, я завёл только лид — потому панель и показывает
«ответов нет».

    python sobytie_vzno.py            # показать
    python sobytie_vzno.py primenit   # дописать событие
"""
import sqlite3
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402
from sender.store import Store                # noqa: E402

ДЕЛАТЬ = "primenit" in sys.argv[1:]
ЯЩИК = "v.melnikov@kompressor-air-trade.ru"
ОТПР = "deev@vzno.ru"

cfg = Config.load(r"C:\sender\sender.yaml")
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")
c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
rec = c.execute("SELECT id, email, company_name FROM recipients WHERE email=?",
                (ОТПР,)).fetchone()
print("получатель #%s %s" % (rec["id"], rec["company_name"]))
for e in c.execute("SELECT id, event_type, event_ts FROM events "
                   " WHERE recipient_id=? ORDER BY id", (rec["id"],)):
    print("   событие #%s %s %s" % (e["id"], e["event_type"],
                                    str(e["event_ts"])[:19]))

mb = MailBrowser(cfg)
д = mb.messages(ЯЩИК, folder="Spam", limit=20)
цель = next((п for п in (д.get("messages") or [])
             if str(п.get("from_addr") or "").lower() == ОТПР), None)
if цель is None:
    print("письма в спаме больше нет")
    raise SystemExit(0)
полное = mb.message(ЯЩИК, folder="Spam", uid=цель["uid"])
тело = " ".join(str(полное.get("body") or полное.get("text") or "").split())
print("   письмо: %s | %s" % (цель["date_iso"], цель["subject"]))
print("   текст: %s" % тело[:200])

if not ДЕЛАТЬ:
    print("\nвхолостую. Дописать — primenit")
    raise SystemExit(0)

store = Store(БАЗА)
eid, создано = store.append_event(SimpleNamespace(
    dedup_key="spam:%s" % (цель.get("message_id") or "vzno-25-08"),
    event_type="reply",
    event_ts=datetime.fromisoformat(цель.get("date_iso")),
    message_id=None,
    recipient_id=int(rec["id"]),
    campaign_id=None,
    mailbox_id=ЯЩИК,
    provider=None,
    detail={"snippet": тело[:2000], "from": ОТПР,
            "subject": str(цель.get("subject") or ""),
            "papka": "Spam", "istochnik": "сверка спама"}))
print("\nсобытие #%s, создано: %s" % (eid, создано))
c.close()
