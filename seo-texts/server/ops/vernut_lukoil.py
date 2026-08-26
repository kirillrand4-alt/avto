# -*- coding: utf-8 -*-
"""Вернуть «Лукойл» из стоп-листа и завести лид: это было перенаправление.

Служба поддержки ИСУ Снабжение ответила «данный вопрос не относится к
нашей компетенции» и дала три других своих адреса. Правило жалоб приняло
слово «спам» в их корпоративном баннере за жалобу на спам, адрес лёг в
стоп-лист, карточки лида не завелось.

    python vernut_lukoil.py            # показать
    python vernut_lukoil.py primenit   # вернуть
"""
import json
import sqlite3
import sys
import time

sys.path.insert(0, r"C:\sender")

ДЕЛАТЬ = "primenit" in sys.argv[1:]
АДРЕС = "tender@lukoil.com"
БАЗА = r"C:\sender\sender.db"

c = sqlite3.connect(БАЗА, timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row
rec = c.execute("SELECT id, email, company_name, inn FROM recipients "
                " WHERE email=?", (АДРЕС,)).fetchone()
print("получатель #%s %s (%s)" % (rec["id"], rec["email"], rec["company_name"]))
for s in c.execute("SELECT scope, value, reason, source, created_at FROM "
                   "suppression WHERE value=?", (АДРЕС,)):
    print("   в стоп-листе: %s / %s от %s" % (s["reason"], s["source"],
                                              str(s["created_at"])[:19]))
соб = c.execute("SELECT id, detail_json FROM events WHERE recipient_id=? "
                "  AND event_type='complaint' ORDER BY id DESC LIMIT 1",
                (rec["id"],)).fetchone()
текст = ""
if соб:
    текст = " ".join(str(json.loads(соб["detail_json"] or "{}")
                         .get("snippet") or "").split())
    print("   событие #%s: %s" % (соб["id"], текст[:200]))
лид = c.execute("SELECT id FROM leads WHERE recipient_id=?", (rec["id"],)).fetchall()
print("   карточек лида: %d" % len(лид))

if not ДЕЛАТЬ:
    print("\nвхолостую. Вернуть — primenit")
    raise SystemExit(0)

сейчас = time.strftime("%Y-%m-%dT%H:%M:%S")
c.execute("DELETE FROM suppression WHERE value=? AND reason='complaint'", (АДРЕС,))
# Событие было не жалобой, а перенаправлением: чиним вид, чтобы лента и
# счётчик жалоб не врали.
if соб:
    c.execute("UPDATE events SET event_type='reply' WHERE id=?", (соб["id"],))
c.commit()
print("из стоп-листа убран, событие переведено в 'reply'")

from sender.config import Config                              # noqa: E402
from sender.leaddesk import LeadDesk                          # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(БАЗА)
десk = LeadDesk(cfg, store)
r = store.get_recipient(int(rec["id"]))
lid = десk.push_warm_lead(r, "", "[redirect] " + (текст or "перенаправление"),
                          otvetil=АДРЕС)
print("карточка лида: %s" % lid)
c.close()
